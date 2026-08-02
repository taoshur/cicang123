$ErrorActionPreference = "Stop"

$envId = "xingya-d7guuazahac96fea3"
$serviceName = "magnetic-detection"
$port = "8080"

Write-Host "Deploying $serviceName to CloudBase Run environment $envId on port $port..."
tcb.cmd cloudrun deploy -e $envId -s $serviceName --source . --port $port --force
