# Nuitka Commercial Integration Guide

This document describes how to use Nuitka Commercial to compile hyperlib into standalone executables with code protection.

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Build Profiles](#build-profiles)
- [Protection Levels](#protection-levels)
- [Security Considerations](#security-considerations)
- [Key Management](#key-management)
- [Build Output](#build-output)
- [Troubleshooting](#troubleshooting)
- [Advanced Usage](#advanced-usage)

## Overview

Hyperlib supports **Nuitka Commercial** compilation via the CI system. This allows you to:

- Compile Python code to C and then to native machine code
- Create standalone executables (no Python interpreter needed)
- Protect intellectual property with various obfuscation levels
- Encrypt string constants, function names, and tracebacks
- Prevent reverse engineering and code inspection

**Key Features:**

- **CI-Only**: Nuitka compilation is a build-time option, no source code changes needed
- **Dual Output**: Same source produces both standard Python packages and compiled binaries
- **Automatic Installation**: Bootstrap installs Nuitka from HyperSec private PyPI
- **Security Verified**: Ensures Nuitka comes from HyperSec PyPI (not public PyPI)
- **Key Management**: Automatic encryption key generation and storage

## Prerequisites

### 1. System Dependencies

Nuitka requires a C compiler to generate executables:

**Linux (Fedora/RHEL):**
```bash
sudo dnf install gcc gcc-c++ python3-devel
```

**Linux (Debian/Ubuntu):**
```bash
sudo apt-get install build-essential python3-dev
```

**macOS:**
```bash
xcode-select --install
```

**Windows:**
- Visual Studio Build Tools, or
- MinGW-w64

### 2. JFrog Credentials

Nuitka Commercial is hosted on HyperSec's private PyPI. You need JFrog credentials in `.env`:

```bash
# Token auth (preferred)
JF_TOKEN=your-jfrog-access-token
JF_TOKEN_USER=artifactory@hypersec.io

# OR username/password (fallback)
JF_USER=your-email@hypersec.io
JF_PASSWORD=your-jfrog-password
```

### 3. Bootstrap Installation

Bootstrap will automatically install Nuitka when `BUILD_PROFILE=nuitka` is set:

```bash
BUILD_PROFILE=nuitka ./ci/bootstrap --install
```

This will:
1. Check for C compiler (provides hints if missing)
2. Install Nuitka Commercial from HyperSec private PyPI
3. Verify Nuitka source (fails if from public PyPI)
4. Check for commercial features (data-hiding, traceback-encryption)

## Quick Start

### Standard Python Package (Default)

```bash
# Build standard wheel/sdist
./ci/ci build

# Output: dist/*.whl and dist/*.tar.gz
```

### Nuitka Compiled Binary

```bash
# Build with Nuitka (recommended protection)
BUILD_PROFILE=nuitka ./ci/ci build

# Output: dist-nuitka/*.bin (or *.exe on Windows)
#         .keys/*.key (encryption key, if traceback encryption enabled)
```

### Build Locally (Single Architecture)

```bash
# Build Nuitka executable locally (local CPU architecture only)
BUILD_PROFILE=nuitka ./ci/ci build

# Output: dist-nuitka/hyperlib-linux-x64.bin (or -arm64.bin on ARM)
```

**Note**: Local builds compile for **your current CPU architecture only** (x64 or ARM64). This is fast and free, perfect for testing before running expensive multi-arch GitHub Actions builds.

### Multi-Architecture Builds (GitHub Actions)

For production releases, use GitHub Actions to build for **multiple architectures**:

**Supported Platforms** (configurable in `ci/ci.yaml`) - **Private repository pricing**:
- **Linux x64**: `ubuntu-latest` ($0.008/min, ~$0.056 per build)
- **Linux ARM64**: `ubuntu-24.04-arm` ($0.016/min, ~$0.112 per build) - **2x cost, native ARM64!**
- **macOS ARM64**: `macos-latest` ($0.16/min, ~$1.12 per build) - **20x expensive!**

**Note**: Public repos get ARM64 for free, but HyperSec uses **private repositories** which are billed.

**Workflow**: `.github/workflows/nuitka-release.yml`

**Trigger**:
```bash
# Create version tag (automatically triggers multi-arch build)
FORCE_RELEASE=1 ./ci/ci publish
```

**Or manually trigger**:
1. Go to GitHub Actions → Nuitka Multi-Arch Release
2. Click "Run workflow"
3. Optionally force build/publish

**Configuration** (`ci/ci.yaml`):
```yaml
nuitka:
  enabled: true
  platforms:
    linux_x64: true       # Always enable (cheap)
    linux_arm64: true     # Enable if needed (2x cost)
    macos_arm64: false    # EXPENSIVE! (20x cost)
```

**Output**:
- Compiled wheels: `dist/*.whl` (one per architecture)
- Each wheel contains platform-specific `.so` file (Nuitka-compiled)
- Published to JFrog PyPI repository for `pip install`

**Cost Management**:

| Platform | Runner | Cost/min | Build Time | Cost/Build |
|----------|--------|----------|------------|------------|
| Linux x64 | ubuntu-latest | $0.008 | ~7 min | $0.056 |
| Linux ARM64 | ubuntu-24.04-arm | $0.016 | ~7 min | $0.112 |
| macOS ARM64 | macos-latest | $0.16 | ~7 min | $1.12 |

**Monthly costs** (10 releases) - **Private repository pricing**:
- Linux x64 only: $0.56/month
- Linux x64 + ARM64: **$1.68/month** (current config)
- All platforms (including macOS): $13.80/month

**HyperSec Configuration**: Linux x64 + ARM64 enabled, macOS disabled.

**Recommendation**: Keep current config (x64 + ARM64), only enable macOS if Apple Silicon distribution is critical.

**ARM64 Runner Configuration**:

GitHub Actions now provides **native ARM64 Linux runners**:
- **Ubuntu 24.04 ARM64**: `runs-on: ubuntu-24.04-arm` (recommended)
- **Ubuntu 22.04 ARM64**: `runs-on: ubuntu-22.04-arm`

**Setup**:
1. ARM64 runners are available on GitHub-hosted infrastructure
2. Cost: 2x standard Linux runners ($0.016/min vs $0.008/min)
3. Performance: Native ARM64 execution (no emulation needed)

**No additional configuration needed** - just enable in `ci/ci.yaml`:
```yaml
nuitka:
  platforms:
    linux_arm64: true
```

**Alternatives** (if you want to avoid GitHub Actions costs):
- **Self-hosted runner**: Set up your own ARM64 machine (free, but maintenance required)
- **BuildJet**: Third-party ARM64 runners (https://buildjet.com) - may be cheaper for high volume
- **Disable ARM64**: Set `linux_arm64: false` in `ci/ci.yaml` (build x64 only, free)

## Build Profiles

The `BUILD_PROFILE` environment variable controls the build artifact type:

| Profile | Output | Use Case |
|---------|--------|----------|
| `package` (default) | Standard Python wheel/sdist | Library distribution, PyPI publishing |
| `nuitka` | Compiled standalone executable | IP protection, closed-source distribution |

**Examples:**

```bash
# Explicit standard build
BUILD_PROFILE=package ./ci/ci build

# Nuitka build
BUILD_PROFILE=nuitka ./ci/ci build
```

## Protection Levels

The `NUITKA_PROTECTION` environment variable controls code protection features:

### `none` - Basic Compilation Only

```bash
BUILD_PROFILE=nuitka NUITKA_PROTECTION=none ./ci/ci build
```

- **Features**: Standalone executable, no Python interpreter needed
- **Protection**: None (fastest compilation)
- **Use Case**: Testing, performance benchmarks
- **Build Time**: Fastest

### `minimal` - Standalone Mode Only

```bash
BUILD_PROFILE=nuitka NUITKA_PROTECTION=minimal ./ci/ci build
```

- **Features**: Standalone executable
- **Protection**: None
- **Use Case**: Distribution without IP concerns
- **Build Time**: Fast

### `data-hiding` - Encrypt Constants and Names

```bash
BUILD_PROFILE=nuitka NUITKA_PROTECTION=data-hiding ./ci/ci build
```

- **Features**:
  - Encrypts all string constants
  - Obfuscates function and variable names
  - Makes `strings` command output unreadable
- **Protection**: Medium
- **Use Case**: Moderate IP protection
- **Build Time**: Moderate

**What's Protected:**
- String literals
- Function/class/variable names
- Module names
- Constants blob

**What's NOT Protected:**
- Runtime memory (while program is running)
- Network traffic
- Files written to disk

### `traceback` - Encrypt Output and Tracebacks

```bash
BUILD_PROFILE=nuitka NUITKA_PROTECTION=traceback ./ci/ci build
```

- **Features**:
  - Encrypts stdout/stderr
  - Encrypts exception tracebacks
  - Generates decryption key file
- **Protection**: Medium (prevents information leakage)
- **Use Case**: Sensitive error messages, production deployments
- **Build Time**: Moderate

**Output Files:**
- `dist-nuitka/stdout-encrypted.txt` - Encrypted stdout
- `dist-nuitka/stderr-encrypted.txt` - Encrypted stderr
- `.keys/hyperlib-<version>-<timestamp>.key` - Decryption key

**Decrypting Logs:**
```bash
python -m nuitka.tools.commercial.decrypt \
  --key=.keys/hyperlib-1.6.0-20251015T120000.key \
  dist-nuitka/stderr-encrypted.txt
```

### `recommended` - Full Protection Stack (Default)

```bash
BUILD_PROFILE=nuitka ./ci/ci build  # Uses 'recommended' by default
```

- **Features**:
  - All `data-hiding` features
  - All `traceback` features
  - Python isolation mode (prevents external module loading)
- **Protection**: Maximum
- **Use Case**: Production, high-value IP protection
- **Build Time**: Slowest (most comprehensive)

**Python Isolation:**
- Blocks loading of modules not included in compilation
- Prevents code injection attacks
- Most effective with `--standalone` mode

## Security Considerations

### Critical: Source Verification

The bootstrap performs **mandatory source verification**:

```python
# Checks if Nuitka is from public PyPI
if "pypi.org" in metadata or "pypi.python.org" in metadata:
    logger.error("[ERR] SECURITY VIOLATION: Nuitka installed from PUBLIC PyPI!")
    return False
```

**Why This Matters:**
- Public PyPI has open-source Nuitka (lacks commercial features)
- HyperSec private PyPI has Nuitka Commercial (full features)
- Bootstrap **fails hard** if wrong source detected

**Verification Points:**
1. Bootstrap install time (during `./ci/bootstrap --install`)
2. Build time (before compilation starts)
3. Manual check: `pip show nuitka` (should not mention pypi.org)

### Encryption Key Security

When using `traceback` or `recommended` protection, encryption keys are generated:

**Key Storage:**
- Location: `.keys/hyperlib-<version>-<timestamp>.key`
- Gitignored: Yes (automatically, never commit!)
- Required for: Decrypting logs and tracebacks from compiled binaries

**Security Checklist:**

- [ ] Backup keys securely (password manager, key vault)
- [ ] Store keys separate from binaries
- [ ] Limit key access to authorized personnel
- [ ] Document key location for operations team
- [ ] Rotate keys periodically (rebuild with new keys)
- [ ] Never commit keys to version control
- [ ] Never distribute keys with binaries

**Key Management Best Practices:**

1. **Secure Storage**: AWS Secrets Manager, HashiCorp Vault, Azure Key Vault
2. **Access Control**: Use IAM/RBAC to restrict key access
3. **Auditing**: Log all key access and usage
4. **Backup**: Keep encrypted backups in multiple secure locations
5. **Rotation**: Generate new keys for each major release

### Security Banner

When traceback encryption is enabled, the build prints a prominent warning:

```
################################################################
#                                                              #
#            CRITICAL: ENCRYPTION KEY GENERATED                #
#                                                              #
#  A new encryption key has been created for this build:      #
#                                                              #
#    .keys/hyperlib-1.6.0-20251015T120000.key                 #
#                                                              #
#  THIS KEY IS REQUIRED TO DECRYPT LOGS AND TRACEBACKS!       #
#                                                              #
#  Security Checklist:                                         #
#    [ ] Key is backed up securely (password manager, vault)  #
#    [ ] Key is NOT committed to git (already in .gitignore)  #
#    [ ] Access to key is restricted to authorized personnel  #
#    [ ] Key location is documented for operations team       #
#                                                              #
################################################################
```

**DO NOT IGNORE THIS WARNING!** Without the key, you cannot decrypt logs from your compiled binary.

## Key Management

### Key Directory Structure

```
.keys/
├── README.md                              # Key management documentation
├── hyperlib-1.6.0-20251015T120000.key    # Encryption key (NEVER COMMIT!)
└── hyperlib-1.6.1-20251016T140000.key    # Another build's key
```

### Decrypting Logs

After running a Nuitka-compiled binary:

```bash
# Binary writes encrypted logs
./dist-nuitka/hyperlib.bin > stdout-encrypted.txt 2> stderr-encrypted.txt

# Decrypt using key
python -m nuitka.tools.commercial.decrypt \
  --key=.keys/hyperlib-1.6.0-20251015T120000.key \
  stdout-encrypted.txt

python -m nuitka.tools.commercial.decrypt \
  --key=.keys/hyperlib-1.6.0-20251015T120000.key \
  stderr-encrypted.txt
```

### Key Lifecycle

1. **Generation**: Automatic during Nuitka build (when traceback encryption enabled)
2. **Storage**: `.keys/` directory (gitignored)
3. **Backup**: Manual (use secure storage)
4. **Rotation**: Rebuild with new key for new version
5. **Retirement**: Archive old keys (for decrypting old logs)

## Build Output

### Directory Structure

```
hyperlib/
├── dist/                      # Standard Python builds
│   ├── hyperlib-1.6.0.tar.gz # Source distribution
│   └── hyperlib-1.6.0-py3-none-any.whl  # Wheel
│
├── dist-nuitka/              # Nuitka compiled builds
│   ├── hyperlib.bin          # Linux binary (or .exe on Windows)
│   ├── stdout-encrypted.txt  # Encrypted stdout (if traceback encryption)
│   └── stderr-encrypted.txt  # Encrypted stderr (if traceback encryption)
│
└── .keys/                    # Encryption keys (NEVER COMMIT!)
    ├── README.md
    └── hyperlib-1.6.0-20251015T120000.key
```

### Build Artifacts

**Standard Build** (`BUILD_PROFILE=package`):
- `dist/*.whl` - Wheel distribution
- `dist/*.tar.gz` - Source distribution

**Nuitka Build** (`BUILD_PROFILE=nuitka`):
- `dist-nuitka/*.bin` - Compiled binary (Linux)
- `dist-nuitka/*.exe` - Compiled binary (Windows)
- `.keys/*.key` - Encryption key (if traceback encryption enabled)

### Binary Size

Nuitka binaries are typically larger than standard Python packages:

- **Standard wheel**: ~50-100 KB
- **Nuitka binary**: 10-50 MB (includes Python interpreter and dependencies)

Use `--onefile` (already enabled) to create a single executable file.

## Troubleshooting

### C Compiler Not Found

**Symptoms:**
```
[ERR] No C compiler found (gcc or clang required)
```

**Solution:**

Install C compiler for your platform (see [Prerequisites](#prerequisites)).

### Nuitka Source Verification Failed

**Symptoms:**
```
[ERR] SECURITY VIOLATION: Nuitka installed from PUBLIC PyPI!
```

**Cause:** Nuitka was installed from public PyPI (pypi.org) instead of HyperSec private PyPI.

**Solution:**
```bash
# Uninstall wrong Nuitka
ci/.venv/bin/pip uninstall nuitka -y

# Reinstall from HyperSec private PyPI
BUILD_PROFILE=nuitka ./ci/bootstrap --install
```

### Commercial Features Not Detected

**Symptoms:**
```
[WARN] Nuitka installed but commercial plugins not detected
       data-hiding plugin: NOT FOUND
       traceback-encryption plugin: NOT FOUND
```

**Cause:** Open-source Nuitka installed instead of Nuitka Commercial.

**Solution:**
1. Verify JFrog credentials in `.env`
2. Uninstall and reinstall: `ci/.venv/bin/pip uninstall nuitka && BUILD_PROFILE=nuitka ./ci/bootstrap --install`

### Build Timeout

**Symptoms:**
Nuitka build takes a very long time or times out.

**Solution:**
- Nuitka compilation is slow (can take 5-10 minutes)
- Use `NUITKA_PROTECTION=none` for faster testing builds
- Increase timeout in CI configuration if needed

### Missing Key File

**Symptoms:**
```
FileNotFoundError: .keys/hyperlib-1.6.0-20251015T120000.key
```

**Cause:** Encryption key was deleted or not generated.

**Solution:**
- Rebuild with traceback encryption enabled
- Check if `.keys/` directory exists and is not gitignored (it should be!)
- Backup keys immediately after generation

### Binary Won't Run

**Symptoms:**
- `./dist-nuitka/hyperlib.bin: Permission denied`
- Segmentation fault
- ImportError for missing modules

**Solutions:**

1. **Permission denied:**
   ```bash
   chmod +x dist-nuitka/hyperlib.bin
   ```

2. **Missing modules:**
   - Add explicit includes: `--include-module=<module>`
   - Use `--follow-imports` to include all dependencies

3. **Segmentation fault:**
   - Try `NUITKA_PROTECTION=none` to isolate issue
   - Check Nuitka version compatibility
   - Report to Nuitka Commercial support

## Advanced Usage

### Custom Nuitka Options

To add custom Nuitka options, edit [ci/python/ci.d/85-build-nuitka.py:135](/ci/python/ci.d/85-build-nuitka.py#L135):

```python
def get_nuitka_command(protection: str, output_dir: Path, keys_dir: Path, key_filename: str) -> list:
    # Base command
    cmd = [
        sys.executable, "-m", "nuitka",
        "--standalone",
        "--output-dir", str(output_dir),
        # Add your custom options here
        "--include-module=mymodule",
        "--follow-imports",
    ]
```

### Including Data Files

To include non-Python files in the binary:

```python
cmd.extend([
    "--include-data-files=config.yaml=config.yaml",
    "--include-data-dir=templates=templates",
])
```

### Platform-Specific Builds

Nuitka binaries are platform-specific:

- Linux binary (`*.bin`) only runs on Linux
- Windows binary (`*.exe`) only runs on Windows
- macOS binary only runs on macOS

For multi-platform distribution, build on each platform separately.

### Testing Protected Code

To verify protection is working:

```bash
# Build with protection
BUILD_PROFILE=nuitka NUITKA_PROTECTION=data-hiding ./ci/ci build

# Check if strings are hidden (should return nothing)
strings dist-nuitka/hyperlib.bin | grep "YourSecretString"

# If output is empty, data-hiding is working!
```

## Performance Considerations

### Build Time Comparison

| Protection Level | Build Time | Binary Size | Protection |
|-----------------|------------|-------------|------------|
| none            | ~2 min     | ~15 MB      | None       |
| minimal         | ~3 min     | ~15 MB      | None       |
| data-hiding     | ~5 min     | ~20 MB      | Medium     |
| traceback       | ~5 min     | ~20 MB      | Medium     |
| recommended     | ~8 min     | ~25 MB      | Maximum    |

### Runtime Performance

Nuitka-compiled code typically runs:
- 2-5x faster than CPython (for compute-heavy code)
- Similar speed for I/O-bound code
- Faster startup time (no bytecode compilation)

## Limitations

### What Nuitka Can't Protect

1. **Runtime Memory**: Data in memory while program runs
2. **Network Traffic**: Use TLS/encryption at application level
3. **Files on Disk**: Encrypt files separately
4. **Dynamic Code**: `eval()`, `exec()`, runtime imports

### Incompatible Patterns

Avoid these patterns for best Nuitka compatibility:

- Heavy use of `eval()` or `exec()`
- Dynamic imports that can't be determined statically
- Code generators or template engines
- Plugin systems loading arbitrary Python code
- Extensive `sys.path` manipulation at runtime

### Library Compatibility

Most libraries work, but some require special handling:

- **Django/Flask**: Use `--include-package` for all apps
- **SQLAlchemy**: May need `--follow-imports`
- **NumPy/SciPy**: Use `--enable-plugin=numpy`
- **Pandas**: Works but increases binary size significantly

## References

- **Nuitka Documentation**: See [/projects/Nuitka-commercial](file:///projects/Nuitka-commercial) (local checkout)
- **HyperSec PyPI**: `https://hypersec.jfrog.io/artifactory/api/pypi/hypersec-pypi-local/simple`
- **Bootstrap Implementation**: [ci/python/bootstrap.d/25-check-nuitka.py](/ci/python/bootstrap.d/25-check-nuitka.py)
- **Build Implementation**: [ci/python/ci.d/85-build-nuitka.py](/ci/python/ci.d/85-build-nuitka.py)
- **Project State**: [STATE.md](/STATE.md#nuitka-build-profile-code-protection)

## Support

For issues with:
- **Nuitka Commercial**: Contact Nuitka Commercial support
- **HyperSec PyPI**: Contact your JFrog administrator
- **This Implementation**: File an issue or contact the hyperlib team
