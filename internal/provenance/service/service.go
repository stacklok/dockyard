// Package service implements the provenance service layer
package service

import (
	"context"
	"fmt"
	"sync"

	"github.com/stacklok/dockyard/internal/provenance/domain"
)

// Service coordinates provenance verification across different verifiers
type Service struct {
	verifiers map[domain.PackageProtocol]domain.ProvenanceVerifier
	mu        sync.RWMutex
}

// New creates a new provenance service
func New() *Service {
	return &Service{
		verifiers: make(map[domain.PackageProtocol]domain.ProvenanceVerifier),
	}
}

// RegisterVerifier registers a verifier for a specific protocol
func (s *Service) RegisterVerifier(protocol domain.PackageProtocol, verifier domain.ProvenanceVerifier) error {
	if verifier == nil {
		return fmt.Errorf("verifier cannot be nil")
	}

	if !verifier.SupportsProtocol(protocol) {
		return fmt.Errorf("verifier does not support protocol %s", protocol)
	}

	s.mu.Lock()
	defer s.mu.Unlock()

	s.verifiers[protocol] = verifier
	return nil
}

// VerifyProvenance verifies the provenance of a package
func (s *Service) VerifyProvenance(ctx context.Context, pkg domain.PackageIdentifier) (*domain.ProvenanceResult, error) {
	s.mu.RLock()
	verifier, ok := s.verifiers[pkg.Protocol]
	s.mu.RUnlock()

	if !ok {
		return &domain.ProvenanceResult{
			PackageID:    pkg,
			Status:       domain.ProvenanceStatusUnknown,
			ErrorMessage: fmt.Sprintf("no verifier registered for protocol %s", pkg.Protocol),
		}, nil
	}

	result, err := verifier.Verify(ctx, pkg)
	if err != nil {
		return &domain.ProvenanceResult{
			PackageID:    pkg,
			Status:       domain.ProvenanceStatusError,
			ErrorMessage: err.Error(),
		}, err
	}

	return result, nil
}

// BatchVerify verifies multiple packages in parallel
func (s *Service) BatchVerify(ctx context.Context, packages []domain.PackageIdentifier) ([]*domain.ProvenanceResult, error) {
	results := make([]*domain.ProvenanceResult, len(packages))
	errors := make([]error, len(packages))

	var wg sync.WaitGroup
	for i, pkg := range packages {
		wg.Add(1)
		go func(idx int, p domain.PackageIdentifier) {
			defer wg.Done()
			result, err := s.VerifyProvenance(ctx, p)
			results[idx] = result
			errors[idx] = err
		}(i, pkg)
	}

	wg.Wait()

	// Check if any errors occurred
	var firstError error
	for _, err := range errors {
		if err != nil && firstError == nil {
			firstError = err
		}
	}

	return results, firstError
}
