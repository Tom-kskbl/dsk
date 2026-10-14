param(
    [string]$Repo = "night-emo",
    [string]$Tag = "v1.0",
    [switch]$Private
)

# ===========================================================================
# 一键收尾: 授权完成后建仓 + 推送 + 发 Release
#
# 用法(在 night_emo/ 下):
#   powershell -ExecutionPolicy Bypass -File tools\publish.ps1
#   powershell -ExecutionPolicy Bypass -File tools\publish.ps1 -Repo night-emo
#   powershell -ExecutionPolicy Bypass -File tools\publish.ps1 -Private
#
# 四步, 每步都自检:
#   1. gh auth status      未授权则停下并给出授权命令
#   2. gh auth setup-git   把 gh 凭据接给 git, 推送时不再弹登录
#   3. gh repo create      --public --source=. --remote=origin --push
#   4. gh release create   挂上成片 / 混音 / 发布文案 / 联络表
#
# 注意: param() 必须是脚本第一条语句, 说明文字只能放在它下面 ——
#       放在上面会导致 "assignment expression is not valid"。
# ===========================================================================

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

$gh = Join-Path $root "_tools\gh\gh.exe"
if (-not (Test-Path $gh)) { $gh = "gh" }

function Step($msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }
function Fail($msg) { Write-Host "[X] $msg" -ForegroundColor Red; exit 1 }

Step "0. 前置检查"
if (-not (Test-Path ".git")) { Fail "当前目录不是 git 仓库: $root" }
$dirty = (git status --porcelain | Measure-Object -Line).Lines
if ($dirty -gt 0) { Write-Host "  工作区有 $dirty 处未提交改动" -ForegroundColor Yellow }
$mp4 = "out\night01_late_night_emo.mp4"
if (-not (Test-Path $mp4)) { Fail "找不到成片 $mp4" }
Write-Host ("  仓库 HEAD: {0}" -f (git log --oneline -1))
Write-Host ("  成片体积: {0:N1} MB" -f ((Get-Item $mp4).Length / 1MB))

Step "1. 授权状态"
# gh auth status 未登录时以非零码退出; $ErrorActionPreference="Stop" 会把它当异常抛出,
# 所以必须单独 try/catch, 否则脚本在给出提示之前就先崩了。
$status = ""
try { $status = (& $gh auth status 2>&1 | Out-String) } catch { $status = ($_ | Out-String) }
if ($status -notmatch "Logged in to github.com") {
    Write-Host $status
    Write-Host ""
    Write-Host "还没有授权。先跑一次设备码流程(浏览器里点一次 Authorize):" -ForegroundColor Yellow
    Write-Host "  .\_tools\gh\gh.exe auth login --hostname github.com --git-protocol https --skip-ssh-key --web"
    Write-Host "命令会打印一次性码并复制到剪贴板, 浏览器打开 https://github.com/login/device 粘贴授权。"
    exit 2
}
Write-Host "  OK 已授权"

Step "2. 把凭据接给 git"
& $gh auth setup-git 2>&1 | Out-Null
Write-Host "  OK git 已能复用 gh 凭据"

Step "3. 建仓并推送"
& $gh repo view $Repo --json name 2>$null | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-Host "  仓库已存在, 改为配置 remote 并推送"
    $owner = (& $gh api user --jq .login)
    git remote remove origin 2>$null
    git remote add origin "https://github.com/$owner/$Repo.git"
    git push -u origin main
} else {
    $vis = if ($Private) { "--private" } else { "--public" }
    & $gh repo create $Repo $vis --source=. --remote=origin --push
}
if ($LASTEXITCODE -ne 0) { Fail "建仓/推送失败" }
Write-Host "  OK 推送完成"

Step "4. 发 Release"
$assets = @(
    "out\night01_late_night_emo.mp4",
    "out\night01_late_night_emo_mix.wav",
    "out\night01_late_night_emo_posting.md",
    "docs\process\contact_sheet.png"
) | Where-Object { Test-Path $_ }
$notesFile = Join-Path $env:TEMP "night_emo_release_notes.md"
$notes = @(
    "## 深夜效应 · 2 分 57 秒",
    "",
    "1920x1080 / 30fps / H.264 + AAC。",
    "",
    "一支讲「为什么一到凌晨情绪就崩」的像素科普短片，全流程程序化生成:",
    "画面用 pygame 在 640x360 虚拟画布上逐帧绘制, 配音走千问 qwen3-tts-flash,",
    "配乐为程序化合成(70 BPM, A 小调 -> 末段转 C 大调)。",
    "",
    "- 成片: night01_late_night_emo.mp4",
    "- 混音轨: night01_late_night_emo_mix.wav",
    "- 发布文案: night01_late_night_emo_posting.md",
    "- 关键帧联络表: contact_sheet.png",
    "",
    "制作过程与被推翻的设计见仓库 docs/process.md。"
) -join "`n"
[IO.File]::WriteAllText($notesFile, $notes, [Text.UTF8Encoding]::new($false))
& $gh release create $Tag --title "深夜效应 v1.0 (成片 + 素材)" --notes-file $notesFile @assets
if ($LASTEXITCODE -ne 0) { Fail "Release 创建失败" }

Step "完成"
& $gh repo view $Repo --json url,visibility --jq '"  repo: \(.url)  (\(.visibility))"'
& $gh release view $Tag --json url --jq '"  release: \(.url)"'
