// Package pypi implements PyPI/uvx provenance verification using sigstore-go
package pypi

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	"github.com/sigstore/sigstore-go/pkg/verify"

	"github.com/stacklok/dockyard/internal/provenance/domain"
	"github.com/stacklok/dockyard/internal/provenance/sigstore"
)

// Verifier implements provenance verification for PyPI packages using sigstore-go
type Verifier struct {
	httpClient     *http.Client
	simpleURL      string
	bundleVerifier *sigstore.BundleVerifier
}

// NewVerifier creates a new PyPI provenance verifier with sigstore support
func NewVerifier(ctx context.Context) (*Verifier, error) {
	bundleVerifier, err := sigstore.NewBundleVerifier(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to create bundle verifier: %w", err)
	}

	return &Verifier{
		httpClient: &http.Client{
			Timeout: 30 * time.Second,
		},
		simpleURL:      "https://pypi.org/simple",
		bundleVerifier: bundleVerifier,
	}, nil
}

// SupportsProtocol returns true if this verifier supports the given protocol
func (*Verifier) SupportsProtocol(protocol domain.PackageProtocol) bool {
	return protocol == domain.ProtocolPyPI
}

// Verify checks the provenance of a PyPI package
func (v *Verifier) Verify(ctx context.Context, pkg domain.PackageIdentifier) (*domain.ProvenanceResult, error) {
	if pkg.Protocol != domain.ProtocolPyPI {
		return nil, fmt.Errorf("pypi verifier does not support protocol %s", pkg.Protocol)
	}

	// Fetch package metadata from PyPI Simple JSON API (PEP 691)
	simpleMetadata, err := v.fetchSimpleMetadata(ctx, pkg.Name)
	if err != nil {
		return &domain.ProvenanceResult{
			PackageID:    pkg,
			Status:       domain.ProvenanceStatusError,
			ErrorMessage: fmt.Sprintf("failed to fetch package metadata: %v", err),
		}, err
	}

	result := &domain.ProvenanceResult{
		PackageID:        pkg,
		Details:          make(map[string]interface{}),
		AttestationCount: 0,
	}

	// Check for provenance in files matching the version
	var verifiedFiles []string
	var firstPublisher *domain.TrustedPublisher

	for _, file := range simpleMetadata.Files {
		// Check if this file belongs to the specified version
		if strings.Contains(file.Filename, pkg.Version) && file.Provenance != "" {
			result.AttestationCount++

			// Try to verify the provenance
			verified, publisher, err := v.verifyProvenance(ctx, file)
			if err != nil {
				// Has provenance but verification failed
				result.Details[fmt.Sprintf("verification_error_%s", file.Filename)] = err.Error()
				continue
			}

			if verified {
				verifiedFiles = append(verifiedFiles, file.Filename)
				if firstPublisher == nil {
					firstPublisher = publisher
				}
			}
		}
	}

	// Determine status based on verification results
	if len(verifiedFiles) > 0 {
		result.Status = domain.ProvenanceStatusVerified
		result.HasAttestations = true
		result.TrustedPublisher = firstPublisher
		result.Details["verified_files"] = verifiedFiles
	} else if result.AttestationCount > 0 {
		// Has attestations but couldn't verify them
		result.Status = domain.ProvenanceStatusAttestations
		result.HasAttestations = true
		result.ErrorMessage = "attestations found but verification failed"
	} else {
		result.Status = domain.ProvenanceStatusNone
	}

	return result, nil
}

// verifyProvenance verifies a file's provenance using sigstore
func (v *Verifier) verifyProvenance(ctx context.Context, file File) (bool, *domain.TrustedPublisher, error) {
	// Fetch the provenance object
	provenanceData, err := v.fetchProvenanceData(ctx, file.Provenance)
	if err != nil {
		return false, nil, fmt.Errorf("failed to fetch provenance: %w", err)
	}

	// Extract the first attestation bundle
	if len(provenanceData.AttestationBundles) == 0 {
		return false, nil, fmt.Errorf("no attestation bundles in provenance")
	}

	bundle := provenanceData.AttestationBundles[0]
	if len(bundle.Attestations) == 0 {
		return false, nil, fmt.Errorf("no attestations in bundle")
	}

	// Convert the attestation to a Sigstore bundle format
	// PEP 740 attestations are already in Sigstore bundle format
	attestationBytes, err := json.Marshal(bundle.Attestations[0])
	if err != nil {
		return false, nil, fmt.Errorf("failed to marshal attestation: %w", err)
	}

	// Calculate the artifact digest from the file hashes
	var artifactDigest []byte
	if sha256Hash, ok := file.Hashes["sha256"]; ok {
		artifactDigest, err = hex.DecodeString(sha256Hash)
		if err != nil {
			return false, nil, fmt.Errorf("failed to decode sha256 hash: %w", err)
		}
	} else {
		// Download and hash the file
		artifactDigest, err = v.downloadAndHashFile(ctx, file.URL)
		if err != nil {
			return false, nil, fmt.Errorf("failed to hash file: %w", err)
		}
	}

	// Create verification policy options based on publisher info
	var policyOpts []verify.PolicyOption

	// Add certificate identity based on publisher
	if bundle.Publisher.Kind == "GitHub" && bundle.Publisher.Repository != "" {
		certID, err := verify.NewShortCertificateIdentity(
			"https://token.actions.githubusercontent.com",
			"",
			"",
			fmt.Sprintf("^https://github.com/%s/", bundle.Publisher.Repository),
		)
		if err == nil {
			policyOpts = append(policyOpts, verify.WithCertificateIdentity(certID))
		}
	}

	// Verify the bundle with artifact digest
	verifyResult, err := v.bundleVerifier.VerifyBundle(attestationBytes, "sha256", artifactDigest, policyOpts...)
	if err != nil {
		return false, nil, err
	}

	// Create publisher info from the provenance data
	publisher := &domain.TrustedPublisher{
		Kind:       bundle.Publisher.Kind,
		Repository: bundle.Publisher.Repository,
		Workflow:   bundle.Publisher.Workflow,
		Claims:     bundle.Publisher.Claims,
	}

	// Also extract from verification result if available
	if extractedPublisher := sigstore.ExtractPublisherInfo(verifyResult); extractedPublisher != nil {
		if publisher.Kind == "" {
			publisher.Kind = extractedPublisher.Kind
		}
		if publisher.Repository == "" {
			publisher.Repository = extractedPublisher.Repository
		}
	}

	return true, publisher, nil
}

// fetchSimpleMetadata fetches package metadata from PyPI Simple JSON API
func (v *Verifier) fetchSimpleMetadata(ctx context.Context, packageName string) (*SimpleMetadata, error) {
	url := fmt.Sprintf("%s/%s/", v.simpleURL, packageName)

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	// Use PEP 691 JSON format
	req.Header.Set("Accept", "application/vnd.pypi.simple.v1+json")

	resp, err := v.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("failed to fetch package metadata: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("unexpected status code %d: %s", resp.StatusCode, string(body))
	}

	var metadata SimpleMetadata
	if err := json.NewDecoder(resp.Body).Decode(&metadata); err != nil {
		return nil, fmt.Errorf("failed to decode package metadata: %w", err)
	}

	return &metadata, nil
}

// fetchProvenanceData fetches the provenance object from PyPI
func (v *Verifier) fetchProvenanceData(ctx context.Context, provenanceURL string) (*ProvenanceObject, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, provenanceURL, nil)
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	resp, err := v.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("failed to fetch provenance: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("unexpected status code %d", resp.StatusCode)
	}

	var provenance ProvenanceObject
	if err := json.NewDecoder(resp.Body).Decode(&provenance); err != nil {
		return nil, fmt.Errorf("failed to decode provenance: %w", err)
	}

	return &provenance, nil
}

// downloadAndHashFile downloads a file and returns its SHA256 hash
func (v *Verifier) downloadAndHashFile(ctx context.Context, fileURL string) ([]byte, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, fileURL, nil)
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	resp, err := v.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("failed to fetch file: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("unexpected status code %d", resp.StatusCode)
	}

	hasher := sha256.New()
	if _, err := io.Copy(hasher, resp.Body); err != nil {
		return nil, fmt.Errorf("failed to hash file: %w", err)
	}

	return hasher.Sum(nil), nil
}

// SimpleMetadata represents the PyPI Simple JSON API metadata (PEP 691)
type SimpleMetadata struct {
	Name  string `json:"name"`
	Files []File `json:"files"`
}

// File represents a file in the PyPI Simple API
type File struct {
	Filename   string            `json:"filename"`
	URL        string            `json:"url"`
	Provenance string            `json:"provenance,omitempty"`
	Hashes     map[string]string `json:"hashes,omitempty"`
}

// ProvenanceObject represents PEP 740 provenance structure
type ProvenanceObject struct {
	Version            int                 `json:"version"`
	AttestationBundles []AttestationBundle `json:"attestation_bundles"`
}

// AttestationBundle contains attestations and publisher info
type AttestationBundle struct {
	Publisher    Publisher     `json:"publisher"`
	Attestations []interface{} `json:"attestations"`
}

// Publisher contains trusted publisher information
type Publisher struct {
	Kind       string                 `json:"kind"`
	Repository string                 `json:"repository,omitempty"`
	Workflow   string                 `json:"workflow,omitempty"`
	Claims     map[string]interface{} `json:"claims,omitempty"`
}
