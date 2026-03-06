# ═══════════════════════════════════════════════════════════════
# MIZAN (ميزان) — Windows One-Line Installer
# "And the heaven He raised and imposed the balance" — 55:7
#
# Usage (PowerShell):
#   irm https://raw.githubusercontent.com/CodeWithJuber/mizan/main/install.ps1 | iex
#
# Options (set before running):
#   $env:MIZAN_METHOD = "pip"       # pip | git | docker (default: pip)
#   $env:MIZAN_DIR = "$HOME\mizan"  # Install directory for git method
#   $env:MIZAN_BRANCH = "main"      # Git branch
# ═══════════════════════════════════════════════════════════════

$ErrorActionPreference = "Stop"

# ───── Config ─────
$MizanMethod = $(if ($env:MIZAN_METHOD) { $env:MIZAN_METHOD } else { "pip" })
$MizanDir = $(if ($env:MIZAN_DIR) { $env:MIZAN_DIR } else { Join-Path $HOME "mizan" })
$MizanBranch = $(if ($env:MIZAN_BRANCH) { $env:MIZAN_BRANCH } else { "main" })
$MizanRepo = "https://github.com/CodeWithJuber/mizan.git"
$MizanMinPython = "3.11"
$MizanMinNode = 18

# ───── Colors ─────
function Write-Gold { param($Text) Write-Host $Text -ForegroundColor Yellow }
function Write-Info { param($Text) Write-Host "  -> $Text" -ForegroundColor Cyan }
function Write-Ok { param($Text) Write-Host "  [OK] $Text" -ForegroundColor Green }
function Write-Warn { param($Text) Write-Host "  [!] $Text" -ForegroundColor Yellow }
function Write-Err { param($Text) Write-Host "  [X] $Text" -ForegroundColor Red }
function Write-Step { param($Text) Write-Host "`n  --- $Text" -ForegroundColor Yellow }

# ───── Banner ─────
function Show-Banner {
    Write-Host ""
    Write-Gold "    +===============================================+"
    Write-Gold "    |                                               |"
    Write-Gold "    |       MIZAN  -  One-Line Installer            |"
    Write-Gold "    |       Agentic Personal AI System              |"
    Write-Gold "    |                                               |"
    Write-Gold "    +===============================================+"
    Write-Host ""
    Write-Host '    "And He imposed the balance (Mizan)" - Quran 55:7' -ForegroundColor DarkGray
    Write-Host ""
}

# ───── Helpers ─────
function Test-Command { param($Name) return [bool](Get-Command $Name -ErrorAction SilentlyContinue) }

function Get-PythonVersion {
    param($Cmd)
    try {
        $ver = & $Cmd --version 2>&1
        if ($ver -match '(\d+\.\d+)') { return $Matches[1] }
    } catch {}
    return $null
}

function Compare-Version {
    param($Current, $Required)
    $c = [version]$Current
    $r = [version]$Required
    return $c -ge $r
}

# ───── OS Detection ─────
function Get-Platform {
    $arch = $(if ([Environment]::Is64BitOperatingSystem) { "x64" } else { "x86" })
    Write-Info "Detected: Windows ($arch)"
    return @{ OS = "windows"; Arch = $arch }
}

# ───── Python ─────
function Install-PythonIfNeeded {
    Write-Step "Checking Python"

    foreach ($cmd in @("python3", "python", "py")) {
        if (Test-Command $cmd) {
            $ver = Get-PythonVersion $cmd
            if ($ver -and (Compare-Version $ver $MizanMinPython)) {
                Write-Ok "Python $ver found ($cmd)"
                $script:PythonCmd = $cmd
                return
            }
        }
    }

    Write-Warn "Python $MizanMinPython+ not found"
    Write-Info "Installing Python via winget..."

    if (Test-Command "winget") {
        winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements --silent
        # Refresh PATH
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
        $script:PythonCmd = "python"
        Write-Ok "Python installed via winget"
    } else {
        Write-Err "Cannot auto-install Python. Please install Python $MizanMinPython+ from https://www.python.org/downloads/"
        exit 1
    }
}

# ───── Node.js ─────
function Install-NodeIfNeeded {
    Write-Step "Checking Node.js"

    if (Test-Command "node") {
        $ver = (node --version) -replace 'v', ''
        $major = [int]($ver.Split('.')[0])
        if ($major -ge $MizanMinNode) {
            Write-Ok "Node.js v$ver found"
            return
        }
    }

    Write-Warn "Node.js $MizanMinNode+ not found"
    Write-Info "Installing Node.js via winget..."

    if (Test-Command "winget") {
        winget install OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements --silent
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
        Write-Ok "Node.js installed via winget"
    } else {
        Write-Err "Cannot auto-install Node.js. Please install Node.js $MizanMinNode+ from https://nodejs.org/"
        exit 1
    }
}

# ───── Git ─────
function Install-GitIfNeeded {
    if (Test-Command "git") { return }

    Write-Warn "Git not found"
    Write-Info "Installing Git via winget..."

    if (Test-Command "winget") {
        winget install Git.Git --accept-package-agreements --accept-source-agreements --silent
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
        Write-Ok "Git installed via winget"
    } else {
        Write-Err "Cannot auto-install Git. Please install Git from https://git-scm.com/downloads"
        exit 1
    }
}

# ───── Installation Methods ─────

function Install-ViaPip {
    Write-Step "Installing MIZAN via pip"

    $venvDir = Join-Path $HOME ".mizan" "venv"
    if (-not (Test-Path $venvDir)) {
        Write-Info "Creating virtual environment..."
        & $script:PythonCmd -m venv $venvDir
    }

    # Activate venv
    $activateScript = Join-Path $venvDir "Scripts" "Activate.ps1"
    & $activateScript

    Write-Info "Installing mizan package..."
    pip install --upgrade pip -q 2>$null
    try {
        pip install mizan -q 2>$null
        Write-Ok "MIZAN installed via pip"
    } catch {
        Write-Warn "PyPI package not available yet. Falling back to git install..."
        $script:MizanMethod = "git"
        Install-ViaGit
        return
    }

    # Run setup
    Write-Step "Running MIZAN setup"
    try { mizan setup } catch {}

    # Add to PATH
    $binDir = Join-Path $venvDir "Scripts"
    Add-ToPath $binDir
}

function Install-ViaGit {
    Write-Step "Installing MIZAN from source"

    Install-GitIfNeeded

    if (Test-Path $MizanDir) {
        Write-Info "Directory $MizanDir exists, updating..."
        Push-Location $MizanDir
        git pull origin $MizanBranch 2>$null
    } else {
        Write-Info "Cloning MIZAN repository..."
        git clone --branch $MizanBranch --depth 1 $MizanRepo $MizanDir
        Push-Location $MizanDir
    }

    # Backend setup
    Write-Info "Setting up Python environment..."
    & $script:PythonCmd -m venv venv
    $activateScript = Join-Path "venv" "Scripts" "Activate.ps1"
    & $activateScript
    pip install --upgrade pip -q 2>$null
    pip install -e "." -q 2>$null
    Write-Ok "Backend dependencies installed"

    # Frontend setup
    if ($env:MIZAN_SKIP_FRONTEND -ne "1") {
        Write-Info "Setting up frontend..."
        Push-Location (Join-Path $MizanDir "frontend")
        npm install --silent 2>$null
        Write-Ok "Frontend dependencies installed"
        Pop-Location
    }

    # Create .env
    $envFile = Join-Path $MizanDir ".env"
    $envExample = Join-Path $MizanDir ".env.example"
    if (-not (Test-Path $envFile) -and (Test-Path $envExample)) {
        Copy-Item $envExample $envFile
        Write-Warn "Created .env from template - edit with your API keys"
    }

    # Create data directory
    $dataDir = Join-Path $MizanDir "data"
    if (-not (Test-Path $dataDir)) { New-Item -ItemType Directory -Path $dataDir -Force | Out-Null }

    Pop-Location
    Write-Ok "MIZAN installed from source at $MizanDir"
}

function Install-ViaDocker {
    Write-Step "Installing MIZAN via Docker"

    if (-not (Test-Command "docker")) {
        Write-Err "Docker is not installed. Please install Docker Desktop from https://www.docker.com/products/docker-desktop/"
        exit 1
    }

    Install-GitIfNeeded

    if (Test-Path $MizanDir) {
        Push-Location $MizanDir
        git pull origin $MizanBranch 2>$null
    } else {
        git clone --branch $MizanBranch --depth 1 $MizanRepo $MizanDir
        Push-Location $MizanDir
    }

    # Create .env
    $envFile = Join-Path $MizanDir ".env"
    $envExample = Join-Path $MizanDir ".env.example"
    if (-not (Test-Path $envFile)) {
        Copy-Item $envExample $envFile
        Write-Warn "Created .env from template - edit with your API keys before starting"
    }

    Write-Info "Building Docker containers..."
    docker compose build --quiet 2>$null
    Write-Ok "Docker images built"

    Write-Host ""
    Write-Info "Start MIZAN with:"
    Write-Gold "    cd $MizanDir; docker compose up -d"

    Pop-Location
}

# ───── PATH Management ─────

function Add-ToPath {
    param($BinDir)
    $currentPath = [System.Environment]::GetEnvironmentVariable("Path", "User")
    if ($currentPath -notlike "*$BinDir*") {
        [System.Environment]::SetEnvironmentVariable("Path", "$BinDir;$currentPath", "User")
        $env:Path = "$BinDir;$env:Path"
        Write-Info "Added $BinDir to PATH"
    }
}

# ───── Interactive Mode ─────

function Select-Method {
    Write-Host "  Choose installation method:" -ForegroundColor White
    Write-Host ""
    Write-Gold "    1) pip install   (recommended - quick setup)"
    Write-Gold "    2) git clone     (development - full source)"
    Write-Gold "    3) docker        (containerized - production)"
    Write-Host ""

    $choice = Read-Host "  Select [1/2/3] (default: 1)"
    switch ($choice) {
        "1" { $script:MizanMethod = "pip" }
        "2" { $script:MizanMethod = "git" }
        "3" { $script:MizanMethod = "docker" }
        ""  { $script:MizanMethod = "pip" }
        default {
            Write-Err "Invalid choice"
            exit 1
        }
    }
}

# ───── Post-Install ─────

function Show-Success {
    Write-Host ""
    Write-Gold "  ================================================="
    Write-Host "    MIZAN installed successfully!" -ForegroundColor Green
    Write-Gold "  ================================================="
    Write-Host ""

    switch ($MizanMethod) {
        "pip" {
            Write-Host "  Quick Start:" -ForegroundColor White
            Write-Gold "    mizan chat              # Chat in terminal"
            Write-Gold "    mizan serve             # Start API server"
            Write-Host ""
        }
        "git" {
            Write-Host "  Quick Start:" -ForegroundColor White
            Write-Gold "    cd $MizanDir"
            Write-Gold "    .\venv\Scripts\Activate.ps1"
            Write-Gold "    mizan chat              # Chat in terminal"
            Write-Gold "    mizan serve             # Start API server"
            Write-Host ""
        }
        "docker" {
            Write-Host "  Quick Start:" -ForegroundColor White
            Write-Gold "    cd $MizanDir"
            Write-Gold "    # Edit .env with your ANTHROPIC_API_KEY"
            Write-Gold "    docker compose up -d    # Start all services"
            Write-Host ""
        }
    }

    Write-Host "  Important:" -ForegroundColor White
    Write-Host "    Set your API key in .env or environment:" -ForegroundColor Gray
    Write-Host '    $env:ANTHROPIC_API_KEY = "sk-ant-..."' -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  Access:" -ForegroundColor White
    Write-Host "    Frontend:  http://localhost:3000" -ForegroundColor Cyan
    Write-Host "    Backend:   http://localhost:8000" -ForegroundColor Cyan
    Write-Host "    API Docs:  http://localhost:8000/docs" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  Documentation:" -ForegroundColor White
    Write-Host "    https://github.com/CodeWithJuber/mizan" -ForegroundColor Cyan
    Write-Host ""
}

# ───── Main ─────

function Main {
    Show-Banner
    Get-Platform | Out-Null

    # Parse command-line args
    if ($args -contains "--install-method") {
        $idx = [Array]::IndexOf($args, "--install-method")
        if ($idx -lt $args.Length - 1) {
            $script:MizanMethod = $args[$idx + 1]
        }
    }

    # Interactive mode if running in terminal
    if ([Environment]::UserInteractive -and -not $env:MIZAN_METHOD -and -not ($args -contains "--install-method")) {
        Select-Method
    }

    # Prerequisites
    if ($MizanMethod -ne "docker") {
        Install-PythonIfNeeded
        if ($MizanMethod -eq "git" -and $env:MIZAN_SKIP_FRONTEND -ne "1") {
            Install-NodeIfNeeded
        }
    }

    # Install
    switch ($MizanMethod) {
        "pip"    { Install-ViaPip }
        "git"    { Install-ViaGit }
        "docker" { Install-ViaDocker }
        default {
            Write-Err "Unknown method: $MizanMethod. Use: pip, git, or docker"
            exit 1
        }
    }

    Show-Success
}

Main @args
