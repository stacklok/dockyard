// Package sigstore provides common Sigstore verification functionality
package sigstore

import (
	"context"
	"encoding/json"
	"fmt"

	"github.com/sigstore/sigstore-go/pkg/bundle"
	"github.com/sigstore/sigstore-go/pkg/root"
	"github.com/sigstore/sigstore-go/pkg/tuf"
	"github.com/sigstore/sigstore-go/pkg/verify"

	"github.com/stacklok/dockyard/internal/provenance/domain"
)

// BundleVerifier wraps sigstore-go verification functionality
type BundleVerifier struct {
	trustedRoot      *root.TrustedRoot
	verifier         *verify.Verifier
	enabledVerifiers []verify.VerifierOption
}

// NewBundleVerifier creates a new Sigstore bundle verifier
func NewBundleVerifier(_ context.Context) (*BundleVerifier, error) {
	// Initialize TUF client with default options
	opts := tuf.DefaultOptions()
	tufClient, err := tuf.New(opts)
	if err != nil {
		return nil, fmt.Errorf("failed to create TUF client: %w", err)
	}

	// Get trusted root from TUF
	trustedRoot, err := root.GetTrustedRoot(tufClient)
	if err != nil {
		return nil, fmt.Errorf("failed to get trusted root: %w", err)
	}

	// Create verifier with standard options
	verifierOpts := []verify.VerifierOption{
		verify.WithSignedCertificateTimestamps(1), // Require at least 1 SCT
		verify.WithTransparencyLog(1),             // Require at least 1 transparency log entry
		verify.WithObserverTimestamps(1),          // Require at least 1 observer timestamp
	}

	verifier, err := verify.NewVerifier(trustedRoot, verifierOpts...)
	if err != nil {
		return nil, fmt.Errorf("failed to create verifier: %w", err)
	}

	return &BundleVerifier{
		trustedRoot:      trustedRoot,
		verifier:         verifier,
		enabledVerifiers: verifierOpts,
	}, nil
}

// VerifyBundle verifies a Sigstore bundle with artifact digest and additional options
func (bv *BundleVerifier) VerifyBundle(
	bundleData []byte,
	artifactDigest string,
	digestBytes []byte,
	opts ...verify.PolicyOption,
) (*verify.VerificationResult, error) {
	// Parse the bundle
	b := &bundle.Bundle{}
	if err := json.Unmarshal(bundleData, b); err != nil {
		return nil, fmt.Errorf("failed to parse bundle: %w", err)
	}

	// Create the artifact policy
	artifactPolicy := verify.WithArtifactDigest(artifactDigest, digestBytes)

	// Verify the bundle
	result, err := bv.verifier.Verify(b, verify.NewPolicy(artifactPolicy, opts...))
	if err != nil {
		return nil, fmt.Errorf("bundle verification failed: %w", err)
	}

	return result, nil
}

// ExtractPublisherInfo extracts basic publisher information from verification result
// Note: Detailed publisher info is better extracted from the provenance metadata itself
func ExtractPublisherInfo(result *verify.VerificationResult) *domain.TrustedPublisher {
	if result == nil {
		return nil
	}

	publisher := &domain.TrustedPublisher{
		Claims: make(map[string]interface{}),
	}

	// For now, we rely on the publisher information from the provenance metadata
	// (PyPI attestation bundles or npm metadata) rather than extracting from certificates
	// This is simpler and more reliable

	// The verification itself proves the identity via certificate matching,
	// so if verification succeeds, we know the publisher info is trustworthy
	publisher.Kind = "Verified"

	return publisher
}
