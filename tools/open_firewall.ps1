# 以管理员身份运行：为 Python 打开 8090-8099 端口的入站规则，允许机顶盒访问本机 HTTP 服务
# 用法: 右键此文件 -> 使用 PowerShell 运行；或在管理员 PowerShell 中执行本脚本
$ports = 8090..8099
foreach ($p in $ports) {
    $ruleName = "PC2TV Port $p"
    $exists = Get-NetFirewallPortFilter -Protocol TCP | Where-Object { $_.LocalPort -eq $p }
    if (-not $exists) {
        New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Protocol TCP -LocalPort $p -Action Allow | Out-Null
        Write-Host "已添加规则: $ruleName"
    } else {
        Write-Host "规则已存在: $ruleName"
    }
}
Write-Host "完成。若仍未生效，请关闭可能拦截的第三方防火墙/安全软件。"