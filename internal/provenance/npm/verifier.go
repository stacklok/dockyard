// Package npm implements npm/npx provenance verification using sigstore-go
package npm

import (
	"context"
	"crypto/sha512"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"

	"github.com/sigstore/sigstore-go/pkg/verify"

	"github.com/stacklok/dockyard/internal/provenance/domain"
	"github.com/stacklok/dockyard/internal/provenance/sigstore"
)

// Verifier implements provenance verification for npm packages using sigstore-go
type Verifier struct {
	httpClient     *http.Client
	registryURL    string
	bundleVerifier *sigstore.BundleVerifier
}

// NewVerifier creates a new npm provenance verifier with sigstore support
func NewVerifier(ctx context.Context) (*Verifier, error) {
	bundleVerifier, err := sigstore.NewBundleVerifier(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to create bundle verifier: %w", err)
	}

	return &Verifier{
		httpClient: &http.Client{
			Timeout: 30 * time.Second,
		},
		registryURL:    "https://registry.npmjs.org",
		bundleVerifier: bundleVerifier,
	}, nil
}

// SupportsProtocol returns true if this verifier supports the given protocol
func (*Verifier) SupportsProtocol(protocol domain.PackageProtocol) bool {
	return protocol == domain.ProtocolNPM
}

// Verify checks the provenance of an npm package
func (v *Verifier) Verify(ctx context.Context, pkg domain.PackageIdentifier) (*domain.ProvenanceResult, error) {
	if pkg.Protocol != domain.ProtocolNPM {
		return nil, fmt.Errorf("npm verifier does not support protocol %s", pkg.Protocol)
	}

	// Fetch package metadata from npm registry
	metadata, err := v.fetchPackageMetadata(ctx, pkg.Name)
	if err != nil {
		return &domain.ProvenanceResult{
			PackageID:    pkg,
			Status:       domain.ProvenanceStatusError,
			ErrorMessage: fmt.Sprintf("failed to fetch package metadata: %v", err),
		}, err
	}

	// Extract version-specific information
	versionData, ok := metadata.Versions[pkg.Version]
	if !ok {
		return &domain.ProvenanceResult{
			PackageID:    pkg,
			Status:       domain.ProvenanceStatusError,
			ErrorMessage: fmt.Sprintf("version %s not found", pkg.Version),
		}, fmt.Errorf("version %s not found in registry", pkg.Version)
	}

	result := &domain.ProvenanceResult{
		PackageID: pkg,
		Details:   make(map[string]interface{}),
	}

	// Check for attestations (newer provenance format with Sigstore bundles)
	if versionData.Dist.Attestations != nil {
		// Try to verify attestations using sigstore
		verified, publisher, err := v.verifyAttestations(ctx, versionData, pkg)
		if err != nil {
			// Has attestations but verification failed
			result.Status = domain.ProvenanceStatusAttestations
			result.HasAttestations = true
			result.ErrorMessage = fmt.Sprintf("attestation verification failed: %v", err)
			result.Details["verification_error"] = err.Error()
		} else if verified {
			result.Status = domain.ProvenanceStatusVerified
			result.HasAttestations = true
			result.TrustedPublisher = publisher
			result.AttestationCount = 1
		} else {
			result.Status = domain.ProvenanceStatusAttestations
			result.HasAttestations = true
		}
	} else if versionData.Dist.Signatures != nil {
		// Check for signatures (older format, can't verify with sigstore)
		result.HasSignatures = true
		result.Status = domain.ProvenanceStatusSignatures
		result.Details["signatures"] = versionData.Dist.Signatures
	} else {
		result.Status = domain.ProvenanceStatusNone
	}

	// Extract repository information from package metadata
	if metadata.Repository != nil {
		if repoURL, ok := metadata.Repository["url"].(string); ok {
			result.RepositoryURI = repoURL
		}
	}

	return result, nil
}

// verifyAttestations verifies npm attestations using sigstore
func (v *Verifier) verifyAttestations(
	ctx context.Context,
	versionData VersionMetadata,
	pkg domain.PackageIdentifier,
) (bool, *domain.TrustedPublisher, error) {
	// npm attestations can be in different formats
	// Try to extract the attestation URL or bundle data
	attestationData, ok := versionData.Dist.Attestations.(map[string]interface{})
	if !ok {
		return false, nil, fmt.Errorf("attestations in unexpected format")
	}

	// Check if there's a URL to fetch the attestation bundle
	bundleURL, hasURL := attestationData["url"].(string)
	if !hasURL {
		// Attestation data might be embedded
		bundleBytes, err := json.Marshal(attestationData)
		if err != nil {
			return false, nil, fmt.Errorf("failed to marshal attestation data: %w", err)
		}
		return v.verifyBundleData(ctx, bundleBytes, versionData, pkg)
	}

	// Fetch the attestation bundle from URL
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, bundleURL, nil)
	if err != nil {
		return false, nil, fmt.Errorf("failed to create request: %w", err)
	}

	resp, err := v.httpClient.Do(req)
	if err != nil {
		return false, nil, fmt.Errorf("failed to fetch attestation: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return false, nil, fmt.Errorf("unexpected status code %d", resp.StatusCode)
	}

	bundleData, err := io.ReadAll(resp.Body)
	if err != nil {
		return false, nil, fmt.Errorf("failed to read attestation: %w", err)
	}

	return v.verifyBundleData(ctx, bundleData, versionData, pkg)
}

// verifyBundleData verifies a Sigstore bundle
func (v *Verifier) verifyBundleData(
	ctx context.Context,
	bundleData []byte,
	versionData VersionMetadata,
	_ domain.PackageIdentifier,
) (bool, *domain.TrustedPublisher, error) {
	// Calculate the artifact digest (sha512 of the tarball)
	// For npm, we need to hash the tarball
	artifactDigest, err := v.calculateTarballDigest(ctx, versionData.Dist.Tarball)
	if err != nil {
		return false, nil, fmt.Errorf("failed to calculate artifact digest: %w", err)
	}

	// Create verification policy
	// For npm packages, we expect GitHub Actions as the issuer
	certID, err := verify.NewShortCertificateIdentity(
		"https://token.actions.githubusercontent.com",
		"",
		"",
		"^https://github.com/.*",
	)
	if err != nil {
		return false, nil, fmt.Errorf("failed to create certificate identity: %w", err)
	}

	// Verify the bundle with artifact digest and certificate identity
	verifyResult, err := v.bundleVerifier.VerifyBundle(bundleData, "sha512", artifactDigest, verify.WithCertificateIdentity(certID))
	if err != nil {
		return false, nil, err
	}

	// Extract publisher information
	publisher := sigstore.ExtractPublisherInfo(verifyResult)

	return true, publisher, nil
}

// calculateTarballDigest downloads and hashes the tarball
func (v *Verifier) calculateTarballDigest(ctx context.Context, tarballURL string) ([]byte, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, tarballURL, nil)
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	resp, err := v.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("failed to fetch tarball: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("unexpected status code %d", resp.StatusCode)
	}

	hasher := sha512.New()
	if _, err := io.Copy(hasher, resp.Body); err != nil {
		return nil, fmt.Errorf("failed to hash tarball: %w", err)
	}

	digest := hasher.Sum(nil)
	return digest, nil
}

// fetchPackageMetadata fetches the package metadata from the npm registry
func (v *Verifier) fetchPackageMetadata(ctx context.Context, packageName string) (*PackageMetadata, error) {
	url := fmt.Sprintf("%s/%s", v.registryURL, packageName)

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	resp, err := v.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("failed to fetch package metadata: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("unexpected status code %d: %s", resp.StatusCode, string(body))
	}

	var metadata PackageMetadata
	if err := json.NewDecoder(resp.Body).Decode(&metadata); err != nil {
		return nil, fmt.Errorf("failed to decode package metadata: %w", err)
	}

	return &metadata, nil
}

// PackageMetadata represents the npm package metadata structure
type PackageMetadata struct {
	Name       string                     `json:"name"`
	Versions   map[string]VersionMetadata `json:"versions"`
	Repository map[string]interface{}     `json:"repository"`
}

// VersionMetadata represents metadata for a specific package version
type VersionMetadata struct {
	Version string `json:"version"`
	Dist    Dist   `json:"dist"`
}

// Dist represents the distribution information for a package version
type Dist struct {
	Attestations interface{} `json:"attestations,omitempty"`
	Signatures   interface{} `json:"signatures,omitempty"`
	Tarball      string      `json:"tarball"`
	Shasum       string      `json:"shasum"`
	Integrity    string      `json:"integrity"`
}
