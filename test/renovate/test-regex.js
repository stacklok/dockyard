#!/usr/bin/env node

/**
 * Test script for Renovate custom manager regex patterns
 * This script validates that the regex patterns in renovate.json
 * correctly match the spec.yaml files in the project.
 */

const fs = require('fs');
const path = require('path');
const { glob } = require('glob');

// ANSI color codes for output
const colors = {
  reset: '\x1b[0m',
  green: '\x1b[32m',
  red: '\x1b[31m',
  yellow: '\x1b[33m',
  cyan: '\x1b[36m',
  gray: '\x1b[90m'
};

// Load Renovate configuration
function loadRenovateConfig() {
  const configPath = path.join(__dirname, '../../renovate.json');
  try {
    const content = fs.readFileSync(configPath, 'utf8');
    return JSON.parse(content);
  } catch (error) {
    console.error(`${colors.red}✗ Failed to load renovate.json:${colors.reset}`, error.message);
    process.exit(1);
  }
}

// Extract regex patterns from custom managers
function extractRegexPatterns(config) {
  const patterns = {};
  
  if (!config.customManagers || !Array.isArray(config.customManagers)) {
    console.error(`${colors.red}✗ No customManagers found in renovate.json${colors.reset}`);
    process.exit(1);
  }
  
  config.customManagers.forEach((manager, index) => {
    const datasource = manager.datasourceTemplate;
    const fileMatch = manager.fileMatch;
    const matchStrings = manager.matchStrings;
    
    if (!patterns[datasource]) {
      patterns[datasource] = {
        description: manager.description,
        filePatterns: [],
        contentPatterns: []
      };
    }
    
    // Convert fileMatch patterns to RegExp
    fileMatch.forEach(pattern => {
      patterns[datasource].filePatterns.push(new RegExp(pattern));
    });
    
    // Convert matchStrings to RegExp
    matchStrings.forEach(pattern => {
      // Replace named capture groups with regular capture groups for testing
      const testPattern = pattern
        .replace(/\(\?<depName>/g, '(')
        .replace(/\(\?<currentValue>/g, '(');
      patterns[datasource].contentPatterns.push(new RegExp(testPattern));
    });
  });
  
  return patterns;
}

// Find all spec files
async function findSpecFiles() {
  const patterns = [
    'npx/**/spec.yaml',
    'npx/**/spec.yml',
    'uvx/**/spec.yaml',
    'uvx/**/spec.yml',
    'go/**/spec.yaml',
    'go/**/spec.yml'
  ];
  
  const files = [];
  for (const pattern of patterns) {
    const matches = await glob(pattern, { cwd: path.join(__dirname, '../..') });
    files.push(...matches);
  }
  
  return files;
}

// Determine datasource based on file path
function getDatasourceForFile(filePath) {
  if (filePath.startsWith('npx/')) return 'npm';
  if (filePath.startsWith('uvx/')) return 'pypi';
  if (filePath.startsWith('go/')) return 'go';
  return null;
}

// Test a single file
function testFile(filePath, patterns) {
  const fullPath = path.join(__dirname, '../..', filePath);
  const content = fs.readFileSync(fullPath, 'utf8');
  const datasource = getDatasourceForFile(filePath);
  
  if (!datasource || !patterns[datasource]) {
    return {
      file: filePath,
      datasource,
      fileMatchPassed: false,
      contentMatchPassed: false,
      error: `No pattern configured for datasource: ${datasource}`
    };
  }
  
  const pattern = patterns[datasource];
  
  // Test file path pattern
  const fileMatchPassed = pattern.filePatterns.some(regex => regex.test(filePath));
  
  // Test content pattern
  let contentMatchPassed = false;
  let extractedPackage = null;
  let extractedVersion = null;
  
  for (const regex of pattern.contentPatterns) {
    const match = content.match(regex);
    if (match) {
      contentMatchPassed = true;
      extractedPackage = match[1]?.trim();
      extractedVersion = match[2]?.trim();
      break;
    }
  }
  
  return {
    file: filePath,
    datasource,
    fileMatchPassed,
    contentMatchPassed,
    extractedPackage,
    extractedVersion
  };
}

// Main test function
async function runTests() {
  console.log(`${colors.cyan}═══════════════════════════════════════════════════════════${colors.reset}`);
  console.log(`${colors.cyan}  Renovate Custom Manager Regex Test${colors.reset}`);
  console.log(`${colors.cyan}═══════════════════════════════════════════════════════════${colors.reset}\n`);
  
  // Load configuration
  console.log(`${colors.gray}Loading renovate.json...${colors.reset}`);
  const config = loadRenovateConfig();
  
  // Extract patterns
  console.log(`${colors.gray}Extracting regex patterns...${colors.reset}`);
  const patterns = extractRegexPatterns(config);
  
  // Find spec files
  console.log(`${colors.gray}Finding spec files...${colors.reset}\n`);
  const specFiles = await findSpecFiles();
  
  if (specFiles.length === 0) {
    console.log(`${colors.yellow}⚠ No spec files found${colors.reset}`);
    return;
  }
  
  console.log(`Found ${colors.cyan}${specFiles.length}${colors.reset} spec files\n`);
  
  // Test each file
  const results = [];
  let passedCount = 0;
  let failedCount = 0;
  
  for (const file of specFiles) {
    const result = testFile(file, patterns);
    results.push(result);
    
    const passed = result.fileMatchPassed && result.contentMatchPassed;
    if (passed) {
      passedCount++;
      console.log(`${colors.green}✓${colors.reset} ${file}`);
      console.log(`  ${colors.gray}Package: ${result.extractedPackage}${colors.reset}`);
      console.log(`  ${colors.gray}Version: ${result.extractedVersion}${colors.reset}`);
    } else {
      failedCount++;
      console.log(`${colors.red}✗${colors.reset} ${file}`);
      if (!result.fileMatchPassed) {
        console.log(`  ${colors.red}File pattern did not match${colors.reset}`);
      }
      if (!result.contentMatchPassed) {
        console.log(`  ${colors.red}Content pattern did not match${colors.reset}`);
      }
      if (result.error) {
        console.log(`  ${colors.red}Error: ${result.error}${colors.reset}`);
      }
    }
    console.log();
  }
  
  // Summary
  console.log(`${colors.cyan}═══════════════════════════════════════════════════════════${colors.reset}`);
  console.log(`${colors.cyan}  Test Summary${colors.reset}`);
  console.log(`${colors.cyan}═══════════════════════════════════════════════════════════${colors.reset}\n`);
  
  console.log(`Total files tested: ${specFiles.length}`);
  console.log(`${colors.green}Passed: ${passedCount}${colors.reset}`);
  console.log(`${colors.red}Failed: ${failedCount}${colors.reset}\n`);
  
  // Exit with appropriate code
  if (failedCount > 0) {
    console.log(`${colors.red}✗ Some tests failed${colors.reset}`);
    process.exit(1);
  } else {
    console.log(`${colors.green}✓ All tests passed!${colors.reset}`);
    process.exit(0);
  }
}

// Run tests
runTests().catch(error => {
  console.error(`${colors.red}✗ Unexpected error:${colors.reset}`, error);
  process.exit(1);
});