// Package domain defines the core provenance domain models and interfaces
package domain

import "context"

// ProvenanceStatus represents the provenance verification status
type ProvenanceStatus string

const (
	// ProvenanceStatusVerified indicates the package has verified provenance
	ProvenanceStatusVerified ProvenanceStatus = "VERIFIED"
	// ProvenanceStatusSignatures indicates the package has signatures (older format)
	ProvenanceStatusSignatures ProvenanceStatus = "SIGNATURES"
	// ProvenanceStatusAttestations indicates the package has attestations
	ProvenanceStatusAttestations ProvenanceStatus = "ATTESTATIONS"
	// ProvenanceStatusTrustedPublisher indicates the package uses a trusted publisher
	ProvenanceStatusTrustedPublisher ProvenanceStatus = "TRUSTED_PUBLISHER"
	// ProvenanceStatusNone indicates no provenance information is available
	ProvenanceStatusNone ProvenanceStatus = "NONE"
	// ProvenanceStatusUnknown indicates the provenance status could not be determined
	ProvenanceStatusUnknown ProvenanceStatus = "UNKNOWN"
	// ProvenanceStatusError indicates an error occurred during verification
	ProvenanceStatusError ProvenanceStatus = "ERROR"
)

// PackageProtocol represents the package protocol/ecosystem
type PackageProtocol string

const (
	// ProtocolNPM represents npm/npx packages
	ProtocolNPM PackageProtocol = "npx"
	// ProtocolPyPI represents PyPI/uvx packages
	ProtocolPyPI PackageProtocol = "uvx"
	// ProtocolGo represents Go packages
	ProtocolGo PackageProtocol = "go"
)

// PackageIdentifier uniquely identifies a package in its ecosystem
type PackageIdentifier struct {
	Protocol PackageProtocol
	Name     string
	Version  string
}

// ProvenanceResult contains the result of a provenance verification
type ProvenanceResult struct {
	PackageID        PackageIdentifier
	Status           ProvenanceStatus
	HasAttestations  bool
	AttestationCount int
	HasSignatures    bool
	TrustedPublisher *TrustedPublisher
	RepositoryURI    string
	ErrorMessage     string
	Details          map[string]interface{}
}

// TrustedPublisher contains information about the trusted publisher
type TrustedPublisher struct {
	Kind       string // e.g., "GitHub", "GitLab"
	Repository string // e.g., "owner/repo"
	Workflow   string // e.g., "release.yml"
	Claims     map[string]interface{}
}

// ProvenanceVerifier defines the interface for verifying package provenance
type ProvenanceVerifier interface {
	// Verify checks the provenance of a package
	Verify(ctx context.Context, pkg PackageIdentifier) (*ProvenanceResult, error)

	// SupportsProtocol returns true if this verifier supports the given protocol
	SupportsProtocol(protocol PackageProtocol) bool
}

// ProvenanceService coordinates provenance verification across different protocols
type ProvenanceService interface {
	// VerifyProvenance verifies the provenance of a package
	VerifyProvenance(ctx context.Context, pkg PackageIdentifier) (*ProvenanceResult, error)

	// BatchVerify verifies multiple packages in parallel
	BatchVerify(ctx context.Context, packages []PackageIdentifier) ([]*ProvenanceResult, error)
}

// ProvenanceValidator validates provenance requirements
type ProvenanceValidator interface {
	// ValidateRequirements checks if the provenance meets the requirements
	ValidateRequirements(result *ProvenanceResult, requirements ProvenanceRequirements) error
}

// ProvenanceRequirements defines what provenance is required
type ProvenanceRequirements struct {
	RequireAttestations     bool
	RequireTrustedPublisher bool
	RequireSignatures       bool
	AllowNone               bool
}

// DefaultRequirements returns the default provenance requirements
func DefaultRequirements() ProvenanceRequirements {
	return ProvenanceRequirements{
		RequireAttestations:     false,
		RequireTrustedPublisher: false,
		RequireSignatures:       false,
		AllowNone:               true, // Warn but don't fail
	}
}
