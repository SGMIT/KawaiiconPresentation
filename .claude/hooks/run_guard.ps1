# Cursor-on-Windows launcher for the shared tamper_guard.py.
# Cursor pipes hook JSON into this script as PowerShell $input. Re-piping that
# through PowerShell strings corrupts encoding; instead collect $input and feed
# UTF-8 bytes to python via redirected stdin.
$ErrorActionPreference = "Continue"
try {
  $here = Split-Path -Parent $MyInvocation.MyCommand.Path
  if (-not $here) { $here = Join-Path (Get-Location) ".claude\hooks" }
  foreach ($dir in @(
      "$env:LOCALAPPDATA\Programs\Python\Python312",
      "$env:LOCALAPPDATA\Programs\Python\Python313",
      "$env:LOCALAPPDATA\Programs\Python\Python311",
      "$env:ProgramFiles\Python312",
      "$env:ProgramFiles\Python313"
    )) {
    if ($dir -and (Test-Path (Join-Path $dir "python3.exe"))) {
      $env:Path = "$dir;" + $env:Path; break
    }
    if ($dir -and (Test-Path (Join-Path $dir "python.exe"))) {
      $env:Path = "$dir;" + $env:Path; break
    }
  }
  $env:PYTHONIOENCODING = "utf-8"
  $env:PYTHONUTF8 = "1"
  $guard = Join-Path $here "tamper_guard.py"

  $py = $null
  foreach ($name in @("python3", "python", "py")) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($cmd) { $py = $cmd.Source; break }
  }
  if (-not $py) {
    [Console]::Out.WriteLine('{"permission":"deny","user_message":"tamper_guard: python3 not found in hook PATH (fail closed)","agent_message":"tamper_guard: python3 not found in hook PATH (fail closed)"}')
    exit 2
  }

  # Drain hook stdin. Prefer $input (Cursor's documented PowerShell path);
  # fall back to Console.In when the host attached a raw pipe.
  $chunks = New-Object System.Collections.Generic.List[string]
  foreach ($item in $input) {
    if ($null -ne $item) { [void]$chunks.Add([string]$item) }
  }
  $payload = [string]::Join("`n", $chunks)
  if (-not $payload) {
    try { $payload = [Console]::In.ReadToEnd() } catch { $payload = "" }
  }
  if (-not $payload) {
    [Console]::Out.WriteLine('{"permission":"deny","user_message":"tamper_guard: empty hook stdin (fail closed)","agent_message":"tamper_guard: empty hook stdin (fail closed)"}')
    exit 2
  }

  $argList = @()
  if ($py -like "*\py.exe") { $argList += "-3" }
  $argList += $guard

  $psi = New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName = $py
  # Quote each arg for Windows CreateProcess.
  $psi.Arguments = ($argList | ForEach-Object {
      $a = "$_"
      if ($a -match '[\s"]') { '"' + ($a -replace '"', '\"') + '"' } else { $a }
    }) -join " "
  $psi.WorkingDirectory = (Split-Path -Parent (Split-Path -Parent $here))
  $psi.UseShellExecute = $false
  $psi.RedirectStandardInput = $true
  $psi.RedirectStandardOutput = $true
  $psi.RedirectStandardError = $true
  $psi.CreateNoWindow = $true
  $psi.StandardOutputEncoding = [System.Text.UTF8Encoding]::new($false)
  $psi.StandardErrorEncoding = [System.Text.UTF8Encoding]::new($false)

  $proc = New-Object System.Diagnostics.Process
  $proc.StartInfo = $psi
  [void]$proc.Start()
  $utf8 = New-Object System.Text.UTF8Encoding $false
  $bytes = $utf8.GetBytes($payload)
  $proc.StandardInput.BaseStream.Write($bytes, 0, $bytes.Length)
  $proc.StandardInput.Close()
  $stdout = $proc.StandardOutput.ReadToEnd()
  $stderr = $proc.StandardError.ReadToEnd()
  $proc.WaitForExit()
  if ($stdout) { [Console]::Out.Write($stdout) }
  if ($stderr) { [Console]::Error.Write($stderr) }
  exit $proc.ExitCode
} catch {
  $msg = "tamper_guard launcher error (fail closed): $($_.Exception.Message)"
  $json = (@{ permission = "deny"; user_message = $msg; agent_message = $msg } | ConvertTo-Json -Compress)
  [Console]::Out.WriteLine($json)
  exit 2
}
