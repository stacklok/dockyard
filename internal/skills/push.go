package skills

import (
	"context"
	"fmt"
	"log/slog"

	ociskills "github.com/stacklok/toolhive-core/oci/skills"
)

// PushSkill pushes a built skill OCI artifact to a remote registry.
// The BuildResult must contain a valid store and package result.
func PushSkill(ctx context.Context, result *BuildResult) error {
	registry, err := ociskills.NewRegistry()
	if err != nil {
		return fmt.Errorf("creating registry client: %w", err)
	}

	ref := result.ImageRef
	digest := result.PackageResult.IndexDigest

	slog.Info("Pushing skill artifact", "ref", ref, "digest", digest.String())

	if err := registry.Push(ctx, result.Store, digest, ref); err != nil {
		return fmt.Errorf("pushing skill to %s: %w", ref, err)
	}

	slog.Info("Skill artifact pushed successfully", "ref", ref)

	return nil
}
