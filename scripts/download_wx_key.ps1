$ProjectDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $ProjectDir

$env:PYTHONIOENCODING = "utf-8"
python "$ProjectDir\wechat.py" download-wx-key @args
exit $LASTEXITCODE
