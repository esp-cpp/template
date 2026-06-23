#!/usr/bin/env python3
"""Set up a new project from the ESP++ template."""

import argparse
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import urllib.request
import urllib.error
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.parent.resolve()
VALID_TARGETS = ['esp32', 'esp32s2', 'esp32s3', 'esp32c3', 'esp32c6', 'esp32h2']

GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
BOLD = '\033[1m'
RESET = '\033[0m'


def _version_key(path):
    """Extract (major, minor) version tuple from a path for numeric sorting."""
    m = re.search(r'v?(\d+)\.(\d+)', str(path))
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def ask(prompt, default=None):
    suffix = f' [{default}]' if default else ''
    value = input(f'{prompt}{suffix}: ').strip()
    return value if value else default


def _github_anchor(text):
    """Approximate GitHub's heading-to-anchor slug (lowercase, spaces → hyphens)."""
    anchor = re.sub(r'[^\w\s-]', '', text.strip().lower())
    return re.sub(r'\s+', '-', anchor)


def update_readme(app_name):
    """Retitle the README and strip the template setup instructions. Returns a change description or None."""
    path = SCRIPT_DIR / 'README.md'
    if not path.exists():
        return None
    content = original = path.read_text(encoding='utf-8')

    # Retitle the project (H1 heading + the matching table-of-contents entry)
    content = content.replace('# ESP++ Template\n', f'# {app_name}\n', 1)
    content = content.replace(
        '- [ESP++ Template](#esp-template)',
        f'- [{app_name}](#{_github_anchor(app_name)})',
        1,
    )

    # Drop the Automated/Manual Setup entries from the table of contents
    content = re.sub(r'[ \t]*- \[Automated Setup\]\(#automated-setup\)\n', '', content)
    content = re.sub(r'[ \t]*- \[Manual Setup\]\(#manual-setup\)\n', '', content)

    # Remove the Automated Setup and Manual Setup sections — they only apply
    # before the template has been instantiated.
    content = re.sub(
        r'### Automated Setup\n.*?(?=### Use within a Private Repository)',
        '',
        content,
        flags=re.DOTALL,
    )

    if content == original:
        return None
    path.write_text(content, encoding='utf-8')
    return 'README.md             retitled, template setup instructions removed'


def find_idf_path():
    """Return the ESP-IDF installation path, or None if undetectable."""
    # 1. IDF_PATH env var (set when IDF environment is activated)
    if os.environ.get('IDF_PATH'):
        return Path(os.environ['IDF_PATH'])

    # 2. idf.currentSetup in .vscode/settings.json (set by this script or VS Code)
    vscode_settings = SCRIPT_DIR / '.vscode' / 'settings.json'
    if vscode_settings.exists():
        try:
            settings = json.loads(vscode_settings.read_text(encoding='utf-8'))
            setup = settings.get('idf.currentSetup')
            if setup and Path(setup).is_dir():
                return Path(setup)
        except (json.JSONDecodeError, OSError):
            pass

    # 3. Common Windows installation paths
    import glob
    for p in sorted(glob.glob(r'C:\Espressif\frameworks\esp-idf-v*'), reverse=True):
        if Path(p).is_dir():
            return Path(p)

    return None


def read_idf_full_version(idf_path):
    """Return the full IDF version (vX.Y.Z) from any available source, or None."""
    # version.txt
    version_file = idf_path / 'version.txt'
    if version_file.exists():
        m = re.search(r'v?(\d+\.\d+(?:\.\d+)?)', version_file.read_text())
        if m:
            return f'v{m.group(1)}'

    # tools/cmake/version.cmake
    cmake_ver = idf_path / 'tools' / 'cmake' / 'version.cmake'
    if cmake_ver.exists():
        content = cmake_ver.read_text()
        major = re.search(r'IDF_VERSION_MAJOR\s+(\d+)', content)
        minor = re.search(r'IDF_VERSION_MINOR\s+(\d+)', content)
        patch = re.search(r'IDF_VERSION_PATCH\s+(\d+)', content)
        if major and minor:
            p = f'.{patch.group(1)}' if patch else '.0'
            return f'v{major.group(1)}.{minor.group(1)}{p}'

    # Derive from path components (e.g. C:\esp\v6.0\esp-idf → v6.0.0)
    for part in reversed(idf_path.parts):
        m = re.match(r'v?(\d+\.\d+)', part)
        if m:
            return f'v{m.group(1)}.0'

    return None


def detect_idf_version():
    """Return the installed IDF version as 'vX.Y', or None if undetectable."""
    idf_path = find_idf_path()
    if idf_path:
        os.environ['IDF_PATH'] = str(idf_path)
        full = read_idf_full_version(idf_path)
        if full:
            m = re.match(r'v(\d+\.\d+)', full)
            return f'v{m.group(1)}' if m else full
    return None


def find_idf_python():
    """Return the Python executable that has ESP-IDF's venv packages (e.g. click)."""
    try:
        import click  # noqa: F401
        return sys.executable  # already running inside the IDF venv
    except ImportError:
        pass

    # Prefer the venv that matches the profile already selected
    python_env = os.environ.get('IDF_PYTHON_ENV_PATH')
    if python_env:
        candidate = Path(python_env) / 'Scripts' / 'python.exe'
        if candidate.exists():
            return str(candidate)

    # Fallback: glob, pick latest by version number
    import glob
    roots = [r'C:\Espressif']
    localappdata = os.environ.get('LOCALAPPDATA')
    if localappdata:
        roots.append(os.path.join(localappdata, 'Espressif'))
    candidates = []
    for root in roots:
        candidates += glob.glob(os.path.join(root, 'tools', 'python', '*', 'venv', 'Scripts', 'python.exe'))
    candidates.sort(key=_version_key, reverse=True)
    return candidates[0] if candidates else None


def get_github_remote():
    """Return (owner, repo) parsed from the git remote, or None if unavailable."""
    try:
        url = subprocess.check_output(
            ['git', 'remote', 'get-url', 'origin'],
            cwd=SCRIPT_DIR, stderr=subprocess.DEVNULL, text=True
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    # HTTPS: https://github.com/owner/repo.git
    # SSH:   git@github.com:owner/repo.git
    m = re.search(r'github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$', url)
    return (m.group(1), m.group(2)) if m else None


def get_github_token():
    """Try gh CLI silently, then fall back to prompting the user."""
    try:
        token = subprocess.check_output(
            ['gh', 'auth', 'token'], stderr=subprocess.DEVNULL, text=True
        ).strip()
        if token:
            return token
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    return None


def get_github_token_interactive():
    """Prompt the user for a GitHub token."""
    token = get_github_token()
    if token:
        return token
    print(f'  {YELLOW}gh CLI not found or not authenticated.{RESET}')
    print('  Generate a token at: https://github.com/settings/tokens')
    print('  Required scope: repo (or Actions read/write)')
    return ask('  GitHub personal access token (leave blank to skip)') or None


def get_workflow_permissions(owner, repo, token):
    """Return current default_workflow_permissions ('read' or 'write'), or None on error."""
    url = f'https://api.github.com/repos/{owner}/{repo}/actions/permissions/workflow'
    req = urllib.request.Request(
        url,
        headers={
            'Authorization': f'Bearer {token}',
            'Accept': 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2022-11-28',
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())['default_workflow_permissions']
    except (urllib.error.HTTPError, KeyError):
        return None


def set_workflow_permissions(owner, repo, token):
    """Enable read/write workflow permissions via GitHub API."""
    url = f'https://api.github.com/repos/{owner}/{repo}/actions/permissions/workflow'
    payload = json.dumps({
        'default_workflow_permissions': 'write',
        'can_approve_pull_request_reviews': False,
    }).encode()
    req = urllib.request.Request(
        url, data=payload, method='PUT',
        headers={
            'Authorization': f'Bearer {token}',
            'Accept': 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2022-11-28',
            'Content-Type': 'application/json',
        },
    )
    try:
        urllib.request.urlopen(req)
        return True
    except urllib.error.HTTPError as e:
        print(f'  {RED}GitHub API error {e.code}: {e.reason}{RESET}')
        return False


def update_vscode_idf_setup(idf_path_str):
    """Write idf.currentSetup (and ensure idf.customExtraVars) in .vscode/settings.json. Returns True if changed."""
    vscode_dir = SCRIPT_DIR / '.vscode'
    settings_path = vscode_dir / 'settings.json'
    try:
        settings = json.loads(settings_path.read_text(encoding='utf-8')) if settings_path.exists() else {}
        win_path = idf_path_str.replace('/', '\\')
        changed = settings.get('idf.currentSetup') != win_path or 'idf.customExtraVars' not in settings
        if not changed:
            return False
        settings['idf.currentSetup'] = win_path
        settings.setdefault('idf.customExtraVars', {})
        vscode_dir.mkdir(exist_ok=True)
        settings_path.write_text(json.dumps(settings, indent=2), encoding='utf-8')
        return True
    except (OSError, json.JSONDecodeError):
        return False


def detect_repo_visibility(owner, repo, token):
    """Return True if private, False if public, None if undetermined."""
    url = f'https://api.github.com/repos/{owner}/{repo}'
    headers = {'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read()).get('private')
    except urllib.error.HTTPError as e:
        if e.code == 404 and not token:
            return True  # unauthenticated 404 → almost certainly private
        return None
    except urllib.error.URLError:
        return None


def setup_idf_env_from_profile():
    """Source the Espressif PowerShell profile to populate IDF environment variables."""
    if os.environ.get('IDF_PATH'):
        return  # Already in an IDF environment
    import glob

    def _find_profiles(roots):
        found = []
        for root in roots:
            found += glob.glob(os.path.join(root, 'tools', 'Microsoft.*.PowerShell_profile.ps1'))
        return sorted(found, key=_version_key, reverse=True)

    roots = [r'C:\Espressif']
    localappdata = os.environ.get('LOCALAPPDATA')
    if localappdata:
        roots.append(os.path.join(localappdata, 'Espressif'))

    candidates = _find_profiles(roots)

    if not candidates:
        print(f'{YELLOW}ESP-IDF environment not found.{RESET}')
        print('  Please verify that ESP-IDF is installed.')
        espressif_path = ask('  Enter your Espressif installation folder (or leave blank to skip)')
        if espressif_path:
            candidates = _find_profiles([espressif_path])
        if not candidates:
            return

    if len(candidates) == 1:
        ps1_path = candidates[0]
    else:
        print(f'\nMultiple ESP-IDF versions found:')
        for i, c in enumerate(candidates, 1):
            m = re.search(r'v[\d.]+', Path(c).name)
            label = m.group(0) if m else Path(c).name
            print(f'  [{i}] {label}  ({c})')
        choice = ask('Select ESP-IDF version', default='1')
        try:
            ps1_path = candidates[int(choice) - 1]
        except (ValueError, IndexError):
            ps1_path = candidates[0]
    original_path = os.environ.get('PATH', '')
    key_vars = ['IDF_PATH', 'IDF_TOOLS_PATH', 'IDF_PYTHON_ENV_PATH', 'ESP_IDF_VERSION', 'PATH']
    output_cmds = '; '.join(f'Write-Output "{v}=$env:{v}"' for v in key_vars)
    try:
        result = subprocess.run(
            ['powershell', '-NoProfile', '-Command', f'. "{ps1_path}"; {output_cmds}'],
            capture_output=True, text=True, timeout=30
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return
    if result.returncode != 0:
        return
    for line in result.stdout.splitlines():
        for var in key_vars:
            prefix = f'{var}='
            if line.startswith(prefix):
                value = line[len(prefix):]
                if value:
                    if var == 'PATH' and original_path:
                        # The profile runs with -NoProfile so its PATH is the system PATH only.
                        # Append the user's original PATH so git, gh, pre-commit, etc. stay accessible.
                        os.environ['PATH'] = value + os.pathsep + original_path
                    else:
                        os.environ[var] = value
                break


def main():
    was_in_idf_terminal = bool(os.environ.get('IDF_PATH'))
    setup_idf_env_from_profile()
    sourced_idf_profile = not was_in_idf_terminal and bool(os.environ.get('IDF_PATH'))
    parser = argparse.ArgumentParser(description='Rename this ESP++ template project.')
    parser.add_argument('--name', help='Project name (lowercase, underscores)')
    parser.add_argument('--app-name', dest='app_name', help='Display name for CI')
    parser.add_argument('--target', choices=VALID_TARGETS, help='IDF target chip')
    parser.add_argument('--idf-version', dest='idf_version',
                        help='ESP-IDF version to target, e.g. v5.5.1 (defaults to the detected install)')
    parser.add_argument('--flash-size', dest='flash_size', help='Flash size, bytes or shorthand (e.g. 8M)')
    parser.add_argument('--private', action='store_true', default=None,
                        help='Private repo: updates static_analysis.yml trigger')
    parser.add_argument('--skip-set-target', action='store_true',
                        help='Skip idf.py set-target (useful if already configured)')
    args = parser.parse_args()

    print(f'\n{BOLD}ESP++ Template — Project Setup{RESET}\n')

    repo_name = SCRIPT_DIR.name

    name = args.name
    while not name:
        name = ask('Project name (lowercase, underscores)', default=repo_name)
        if not name:
            print('  Project name is required.')
            name = None
        elif not re.match(r'^[a-z][a-z0-9_]*$', name):
            print('  Use lowercase letters, digits, and underscores only.')
            name = None

    app_name = args.app_name or ask('Display name for CI', default=name)

    skip_set_target = args.skip_set_target
    target = args.target
    while not target and not skip_set_target:
        t = ask(f'Target chip ({"/".join(VALID_TARGETS)}) or "skip"', default='esp32s3')
        if t == 'skip':
            skip_set_target = True
        elif t in VALID_TARGETS:
            target = t
        else:
            print(f'  Invalid. Choose from: {", ".join(VALID_TARGETS)}, or "skip" to skip target configuration')

    raw_flash = args.flash_size or ask('Flash size (bytes or e.g. 4M)', default='8M')
    flash_size = str(int(raw_flash[:-1]) * 1_000_000) if raw_flash.upper().endswith('M') else raw_flash

    programmer_name = f'{name}_programmer'

    def _yml_idf_version(p):
        if p.exists():
            m = re.search(r"IDF_VERSION: '(v[\d.]+)'", p.read_text(encoding='utf-8'))
            return m.group(1) if m else None
        return None

    detected_idf = detect_idf_version()
    build_ver = _yml_idf_version(SCRIPT_DIR / '.github/workflows/build.yml')
    pkg_ver = _yml_idf_version(SCRIPT_DIR / '.github/workflows/package_main.yml')

    # Ask which ESP-IDF version to target. Default to the detected install,
    # falling back to whatever the workflow files already specify.
    default_idf = detected_idf or (build_ver if build_ver == pkg_ver else None)
    if args.idf_version:
        chosen_idf = args.idf_version
    else:
        prompt = 'ESP-IDF version to use (e.g. v5.5.1)'
        if detected_idf:
            prompt += f' — detected {detected_idf}'
        chosen_idf = ask(prompt, default=default_idf)
    if chosen_idf and not chosen_idf.startswith('v'):
        chosen_idf = 'v' + chosen_idf

    idf_already_current = bool(chosen_idf) and build_ver == chosen_idf and pkg_ver == chosen_idf
    idf_version = chosen_idf if (chosen_idf and not idf_already_current) else None

    # GitHub — gather remote + permission intent before doing any long-running work
    remote = get_github_remote()
    if not remote:
        try:
            existing_remotes = subprocess.check_output(
                ['git', 'remote'], cwd=SCRIPT_DIR, stderr=subprocess.DEVNULL, text=True
            ).strip().split()
            print(f'\n  {YELLOW}⚠{RESET}  No GitHub remote detected.')
            github_url = ask('  Enter your GitHub repository URL (leave blank to skip)')
            if github_url:
                m = re.search(r'github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$', github_url)
                if m:
                    cmd = 'set-url' if 'origin' in existing_remotes else 'add'
                    subprocess.run(
                        ['git', 'remote', cmd, 'origin', github_url],
                        cwd=SCRIPT_DIR, capture_output=True
                    )
                    remote = (m.group(1), m.group(2))
                else:
                    print(f'  {YELLOW}⚠{RESET}  Not a valid GitHub URL — skipping workflow permissions.')
        except FileNotFoundError:
            print(f'  {RED}✗{RESET}  git not found — cannot detect or set GitHub remote.')

    github_token = None
    do_set_permissions = False
    permissions_already_set = False
    permissions_no_token = False
    is_private = args.private
    if remote:
        owner, repo = remote
        github_token = get_github_token()

        if is_private is None:
            detected_visibility = detect_repo_visibility(owner, repo, github_token)
            if detected_visibility is not None:
                is_private = detected_visibility
                label = 'private' if is_private else 'public'
                print(f'  {GREEN}✓{RESET} Repository detected as {label}')
            else:
                is_private = ask('Private repository? (y/n)', default='n').lower().startswith('y')

        current_perms = get_workflow_permissions(owner, repo, github_token) if github_token else None
        if current_perms == 'write':
            permissions_already_set = True
        else:
            confirm = ask(
                f'Enable "Read and write" workflow permissions on GitHub ({owner}/{repo})? (y/n)',
                default='y'
            )
            if confirm.lower().startswith('y'):
                github_token = github_token or get_github_token_interactive()
                if github_token:
                    do_set_permissions = True
                else:
                    permissions_no_token = True
    elif is_private is None:
        is_private = ask('Private repository? (y/n)', default='n').lower().startswith('y')

    print()
    changes = []

    if not chosen_idf:
        print(f'{YELLOW}No ESP-IDF version specified — IDF_VERSION will not be changed.{RESET}')

    path = SCRIPT_DIR / 'CMakeLists.txt'
    content = path.read_text(encoding='utf-8')
    if 'project(template)' in content:
        path.write_text(content.replace('project(template)', f'project({name})'), encoding='utf-8')
        changes.append(f'CMakeLists.txt        project(template) → project({name})')

    path = SCRIPT_DIR / 'main' / 'main.cpp'
    if path.exists():
        content = path.read_text(encoding='utf-8')
        if '.tag = "Template"' in content:
            path.write_text(content.replace('.tag = "Template"', f'.tag = "{app_name}"'), encoding='utf-8')
            changes.append(f'main/main.cpp         logger tag "Template" → "{app_name}"')

    path = SCRIPT_DIR / '.github/workflows/build.yml'
    content = path.read_text(encoding='utf-8')
    file_changes = []
    if 'APP_NAME: "Template"' in content:
        content = content.replace('APP_NAME: "Template"', f'APP_NAME: "{app_name}"')
        file_changes.append(f'APP_NAME → "{app_name}"')
    if target and "IDF_TARGET: 'esp32'" in content:
        content = content.replace("IDF_TARGET: 'esp32'", f"IDF_TARGET: '{target}'")
        file_changes.append(f'IDF_TARGET → {target}')
    if "FLASH_TOTAL_OVERRIDE: '1500000'" in content:
        content = content.replace("FLASH_TOTAL_OVERRIDE: '1500000'", f"FLASH_TOTAL_OVERRIDE: '{flash_size}'")
        file_changes.append(f'FLASH_TOTAL_OVERRIDE → {flash_size}')
    if idf_version:
        new_content = re.sub(r"IDF_VERSION: 'v[\d.]+'", f"IDF_VERSION: '{idf_version}'", content)
        if new_content != content:
            content = new_content
            file_changes.append(f'IDF_VERSION → {idf_version}')
    if 'permissions:' not in content:
        content = content.replace(
            '\n\nenv:',
            '\n\npermissions:\n  contents: read\n  pull-requests: write\n\nenv:',
            1,
        )
        file_changes.append('added permissions block')
    if file_changes:
        path.write_text(content, encoding='utf-8')
        changes.append(f'build.yml             {", ".join(file_changes)}')

    path = SCRIPT_DIR / '.github/workflows/package_main.yml'
    content = path.read_text(encoding='utf-8')
    file_changes = []
    if 'APP_NAME: "Template"' in content:
        content = content.replace('APP_NAME: "Template"', f'APP_NAME: "{app_name}"')
        file_changes.append(f'APP_NAME → "{app_name}"')
    if target and "IDF_TARGET: 'esp32'" in content:
        content = content.replace("IDF_TARGET: 'esp32'", f"IDF_TARGET: '{target}'")
        file_changes.append(f'IDF_TARGET → {target}')
    if "FLASH_TOTAL_OVERRIDE: '1500000'" in content:
        content = content.replace("FLASH_TOTAL_OVERRIDE: '1500000'", f"FLASH_TOTAL_OVERRIDE: '{flash_size}'")
        file_changes.append(f'FLASH_TOTAL_OVERRIDE → {flash_size}')
    if idf_version:
        new_content = re.sub(r"IDF_VERSION: 'v[\d.]+'", f"IDF_VERSION: '{idf_version}'", content)
        if new_content != content:
            content = new_content
            file_changes.append(f'IDF_VERSION → {idf_version}')
    if "programmer-name: 'your_programmer'" in content:
        content = content.replace(
            "programmer-name: 'your_programmer'", f"programmer-name: '{programmer_name}'"
        )
        file_changes.append(f'programmer-name → {programmer_name}')
    if file_changes:
        path.write_text(content, encoding='utf-8')
        changes.append(f'package_main.yml      {", ".join(file_changes)}')

    if is_private:
        path = SCRIPT_DIR / '.github/workflows/static_analysis.yml'
        content = path.read_text(encoding='utf-8')
        if 'pull_request_target:' in content:
            content = re.sub(
                r'on:\n(?:[ \t]+#[^\n]*\n)*[ \t]+pull_request_target:\n[ \t]+branches:\n[ \t]+-[^\n]*\n',
                'on: [pull_request]\n',
                content,
            )
            path.write_text(content, encoding='utf-8')
            changes.append('static_analysis.yml   pull_request_target → pull_request')

    idf_path_env = os.environ.get('IDF_PATH')
    if idf_path_env and update_vscode_idf_setup(idf_path_env):
        changes.append(f'.vscode/settings.json  idf.currentSetup → {idf_path_env}')

    if target:
        path = SCRIPT_DIR / 'sdkconfig.defaults'
        content = path.read_text(encoding='utf-8')
        new_content = re.sub(
            r'# (CONFIG_IDF_TARGET="' + re.escape(target) + r'")',
            r'\1',
            content,
        )
        if new_content != content:
            path.write_text(new_content, encoding='utf-8')
            changes.append(f'sdkconfig.defaults    CONFIG_IDF_TARGET="{target}" uncommented')

    readme_change = update_readme(app_name)
    if readme_change:
        changes.append(readme_change)

    def _force_remove(func, path, _):
        os.chmod(path, stat.S_IWRITE)
        func(path)

    # Print file changes before running idf.py so they're visible even if set-target fails
    if changes or idf_already_current:
        print(f'{GREEN}Changes applied:{RESET}')
        for c in changes:
            print(f'  {GREEN}✓{RESET} {c}')
        if idf_already_current:
            print(f'  {GREEN}✓{RESET} build.yml             IDF_VERSION already {chosen_idf}')
            print(f'  {GREEN}✓{RESET} package_main.yml      IDF_VERSION already {chosen_idf}')
    else:
        print(f'{YELLOW}Nothing to change — already renamed?{RESET}')

    # Pre-delete build/ so idf.py fullclean doesn't hit Windows permission errors
    build_dir = SCRIPT_DIR / 'build'
    if build_dir.exists():
        shutil.rmtree(build_dir, onerror=_force_remove)

    idf_path = os.environ.get('IDF_PATH')
    idf_py = Path(idf_path) / 'tools' / 'idf.py' if idf_path else None
    idf_python = find_idf_python()
    print()
    if skip_set_target:
        print(f'  {YELLOW}⚠{RESET}  idf.py set-target skipped')
    elif not target:
        print(f'  {YELLOW}⚠{RESET}  idf.py set-target skipped (no target selected)')
    elif idf_py and idf_py.exists() and idf_python:
        print(f'Running idf.py set-target {target}...')
        env = os.environ.copy()
        env.pop('IDF_TARGET', None)
        # Tell idf.py where its own venv and tools live when not in an IDF terminal
        if idf_python != sys.executable:
            env['IDF_PYTHON_ENV_PATH'] = str(Path(idf_python).parent.parent)
            if 'IDF_TOOLS_PATH' not in env:
                p = Path(idf_python).parent
                while len(p.parts) > 1:
                    p = p.parent
                    if list(p.glob('espidf.constraints.*.txt')):
                        env['IDF_TOOLS_PATH'] = str(p)
                        break
        if 'ESP_IDF_VERSION' not in env:
            full_ver = read_idf_full_version(Path(idf_path))
            if full_ver:
                env['ESP_IDF_VERSION'] = full_ver.lstrip('v')
        result = subprocess.run(
            [idf_python, str(idf_py), 'set-target', target],
            cwd=SCRIPT_DIR, env=env
        )
        if result.returncode == 0:
            print(f'  {GREEN}✓{RESET} idf.py set-target      configured for {target}, build cache cleared')
        else:
            sdkconfig = SCRIPT_DIR / 'sdkconfig'
            if sdkconfig.exists():
                sdkconfig.unlink()
            print(f'  {YELLOW}⚠{RESET}  idf.py set-target failed — sdkconfig cleared manually.')
            print(f'     File changes above are saved. Run manually to finish:')
            print(f'     idf.py set-target {target}')
    elif not idf_python:
        print(f'  {RED}✗{RESET}  ESP-IDF Python environment not found — skipping set-target.')
        print(f'     File changes above are saved. Run manually to finish:')
        print(f'     idf.py set-target {target}')
    else:
        sdkconfig = SCRIPT_DIR / 'sdkconfig'
        if sdkconfig.exists():
            sdkconfig.unlink()
        print(f'  {YELLOW}⚠{RESET}  idf.py not found — sdkconfig cleared manually.')
        print(f'     File changes above are saved. Run manually to finish:')
        print(f'     idf.py set-target {target}')

    # GitHub: apply the permission decision gathered before set-target
    print()
    if remote:
        if permissions_already_set:
            print(f'  {GREEN}✓{RESET} GitHub workflow permissions already set to read/write')
        elif do_set_permissions:
            if set_workflow_permissions(owner, repo, github_token):
                print(f'  {GREEN}✓{RESET} GitHub workflow permissions set to read/write')
            else:
                print(f'  {RED}✗{RESET}  Failed — please set manually in GitHub: Settings → Actions → Workflow Permissions, then re-run this script.')
        elif permissions_no_token:
            print(f'  {RED}✗{RESET}  No token — please set manually in GitHub: Settings → Actions → Workflow Permissions, then re-run this script.')
        # user said 'n' → no output needed

    # Install pre-commit hook
    print()
    precommit_ok = False
    precommit_detail = None
    for cmd in [['pre-commit', 'install'], [sys.executable, '-m', 'pre_commit', 'install']]:
        try:
            r = subprocess.run(cmd, cwd=SCRIPT_DIR, capture_output=True, text=True)
            if r.returncode == 0:
                precommit_ok = True
            else:
                precommit_detail = (r.stdout + r.stderr).strip() or 'non-zero exit code'
            break
        except FileNotFoundError:
            continue

    if precommit_ok:
        print(f'  {GREEN}✓{RESET} pre-commit hook installed (clang-format on commit)')
    elif precommit_detail is not None:
        print(f'  {YELLOW}⚠{RESET}  pre-commit install failed: {precommit_detail}')
        print(f'     Run manually: pre-commit install')
    else:
        print(f'  {YELLOW}⚠{RESET}  pre-commit not found.')
        print(f'     Install it: pip install pre-commit')
        print(f'     Then run:   pre-commit install')

    print(f'\n{YELLOW}Remaining manual steps:{RESET}')
    print('  • Update README.md with your project description and screenshots')
    print('  • Write your application code in main/main.cpp')
    print('  • Add component dependencies:')
    print('      idf.py add-dependency "espp/<component>>=1.0"')
    print('  • To change CPU clock frequency, FreeRTOS tick rate, or task stack sizes:')
    print('    - Run "idf.py menuconfig" for interactive configuration (local only)')
    print('    - Edit sdkconfig.defaults to persist settings globally for all repo users')
    if remote and not permissions_already_set and not do_set_permissions and not permissions_no_token:
        print('  • Set GitHub workflow permissions: Settings → Actions → Workflow Permissions → Read and write')

    print()
    if sourced_idf_profile:
        print(f'{GREEN}Project successfully set up!{RESET}')
        print(f'{YELLOW}Please close this terminal and continue in an ESP-IDF Terminal.{RESET}')
    else:
        print(f'{GREEN}Project successfully set up!{RESET}')
    print()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nAborted.')
