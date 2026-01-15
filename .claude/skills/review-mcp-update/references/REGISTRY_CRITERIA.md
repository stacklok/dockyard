# ToolHive Registry Criteria

This document outlines the criteria used to evaluate MCP servers for inclusion in the ToolHive registry. These criteria ensure servers meet standards of security, quality, and usability.

## Open Source Requirements

### Licensing
- **Required:** Must be fully open source with no exceptions
- **Required:** Source code must be publicly accessible
- **Acceptable licenses:** Apache-2.0, MIT, BSD-2-Clause, BSD-3-Clause
- **Excluded licenses:** AGPL, GPL2, GPL3 (copyleft licenses are excluded to allow broad commercial integration)

## Security Criteria

### Software Provenance
- Sigstore signatures or GitHub Attestations
- SLSA compliance level assessment
- Pinned dependencies and GitHub Actions
- Published Software Bill of Materials (SBOMs)

### Security Practices
- Secure authentication mechanisms
- Proper authorization controls
- Standard security protocol support (OAuth, TLS)
- Encryption for data in transit and at rest
- Clear incident response channels
- Security issue reporting mechanisms (email, GHSA)

## Continuous Integration

- Automated dependency updates (Dependabot, Renovate)
- Automated security scanning
- CVE monitoring
- Code linting and quality checks

## Repository Health Metrics

### Activity Indicators
- Repository stars and forks
- Commit frequency and recency
- Contributor activity
- Issue and pull request statistics

### Responsiveness
- Active maintainer engagement
- Regular commit activity
- **Red flag:** Issues open 3-4 weeks without response
- Bug resolution rate
- User support quality

## API Compliance

- Full MCP API specification support
- Implementation of all required endpoints (tools, resources, etc.)
- Protocol version compatibility

## Code Quality

- Presence of automated tests
- Test coverage percentage
- Quality CI/CD implementation
- Code review practices

## Documentation

- Basic project documentation
- API documentation
- Deployment and operation guides
- Regular documentation updates

## Release Process

- Established CI-based release process
- Regular release cadence
- Semantic versioning compliance
- Maintained changelog

## Tool Stability

- Version consistency
- Breaking change frequency
- Backward compatibility maintenance

## Governance

- Project backing (individual vs. organizational)
- Number of active maintainers
- Contributor diversity
- Corporate or foundation support
- Governance model maturity

## Scoring Framework (Future)

Criteria are categorized as:
- **Required:** Essential attributes (significant penalty if missing)
- **Expected:** Typical well-executed project attributes (moderate score impact)
- **Recommended:** Good practice indicators (positive contribution)
- **Bonus:** Excellence demonstrators (no penalty for absence)

## Tiered Classifications (Future)

- "Verified" vs "Experimental/Community" designations
- Minimum threshold requirements (stars, maintainers, community indicators)
- Regular re-evaluation frequency for automated checks
