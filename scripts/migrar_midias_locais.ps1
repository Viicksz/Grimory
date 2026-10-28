param(
    [switch]$AplicarReferencias
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Net.Http
$raiz = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$pastaFichas = Join-Path $raiz "biblioteca\fichas"
$pastaVassouras = Join-Path $raiz "biblioteca\quadribol\vassouras"
$arquivoImagensVassouras = Join-Path $pastaVassouras "linhas\Imagens.md"
$pastaExportacao = Join-Path $raiz "exports\migracao_midias"

function Get-Slug([string]$Texto) {
    $normalizado = $Texto.Normalize([Text.NormalizationForm]::FormD)
    $semAcentos = -join ($normalizado.ToCharArray() | Where-Object {
        [Globalization.CharUnicodeInfo]::GetUnicodeCategory($_) -ne
            [Globalization.UnicodeCategory]::NonSpacingMark
    })
    $slug = $semAcentos.ToLowerInvariant() -replace "[^a-z0-9]+", "-"
    return $slug.Trim("-")
}

function Get-ExtensaoImagem([byte[]]$Bytes) {
    if ($Bytes.Length -ge 8 -and $Bytes[0] -eq 0x89 -and $Bytes[1] -eq 0x50 -and
        $Bytes[2] -eq 0x4e -and $Bytes[3] -eq 0x47) { return ".png" }
    if ($Bytes.Length -ge 3 -and $Bytes[0] -eq 0xff -and $Bytes[1] -eq 0xd8 -and
        $Bytes[2] -eq 0xff) { return ".jpg" }
    if ($Bytes.Length -ge 12 -and [Text.Encoding]::ASCII.GetString($Bytes, 0, 4) -eq "RIFF" -and
        [Text.Encoding]::ASCII.GetString($Bytes, 8, 4) -eq "WEBP") { return ".webp" }
    throw "O arquivo baixado não é PNG, JPG ou WEBP."
}

function Get-Hash([byte[]]$Bytes) {
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash($Bytes))).Replace("-", "").ToLowerInvariant() }
    finally { $sha.Dispose() }
}

$handler = [System.Net.Http.HttpClientHandler]::new()
$handler.AutomaticDecompression = (
    [Net.DecompressionMethods]::GZip -bor [Net.DecompressionMethods]::Deflate
)
$cliente = [System.Net.Http.HttpClient]::new($handler)
$cliente.Timeout = [TimeSpan]::FromSeconds(45)
$cliente.DefaultRequestHeaders.UserAgent.ParseAdd("Grimory-Media-Migration/1.0")
$registros = [Collections.Generic.List[object]]::new()
$falhas = [Collections.Generic.List[object]]::new()
$discordCliente = $null
$arquivoEnv = Join-Path $raiz ".env"
if (Test-Path -LiteralPath $arquivoEnv) {
    $tokenDiscord = $null
    foreach ($linhaEnv in [IO.File]::ReadAllLines($arquivoEnv, [Text.Encoding]::UTF8)) {
        if ($linhaEnv -match "^\s*(GRIMORY_DISCORD_TOKEN|DISCORD_TOKEN)\s*=\s*(.+?)\s*$") {
            $tokenDiscord = $Matches[2].Trim().Trim('"').Trim("'")
            if ($Matches[1] -eq "GRIMORY_DISCORD_TOKEN") { break }
        }
    }
    if ($tokenDiscord) {
        $discordCliente = [System.Net.Http.HttpClient]::new()
        $discordCliente.Timeout = [TimeSpan]::FromSeconds(30)
        $discordCliente.DefaultRequestHeaders.Authorization =
            [System.Net.Http.Headers.AuthenticationHeaderValue]::new("Bot", $tokenDiscord)
        $discordCliente.DefaultRequestHeaders.UserAgent.ParseAdd("Grimory-Media-Migration/1.0")
    }
}

function Get-UrlDiscordAtualizada([string]$Url) {
    if ($null -eq $discordCliente -or
        $Url -notmatch "discordapp\.(net|com)/attachments/(\d+)/(\d+)/") { return $null }
    $canal = $Matches[2]
    $anexo = $Matches[3]
    $endpoint = "https://discord.com/api/v10/channels/$canal/messages?around=$anexo&limit=25"
    try {
        $json = $discordCliente.GetStringAsync($endpoint).GetAwaiter().GetResult()
        $mensagens = $json | ConvertFrom-Json
        foreach ($mensagem in $mensagens) {
            foreach ($attachment in $mensagem.attachments) {
                if ([string]$attachment.id -eq $anexo) {
                    if ($attachment.proxy_url) {
                        return [string]$attachment.proxy_url
                    }
                    return [string]$attachment.url
                }
            }
        }
    }
    catch { return $null }
    return $null
}

function Get-BytesImagem([string]$Url) {
    $tentativas = [Collections.Generic.List[string]]::new()
    $tentativas.Add($Url)
    $atualizada = Get-UrlDiscordAtualizada $Url
    if ($atualizada -and $atualizada -ne $Url) { $tentativas.Add($atualizada) }
    foreach ($tentativa in $tentativas) {
        $resposta = $cliente.GetAsync($tentativa).GetAwaiter().GetResult()
        try {
            if ($resposta.IsSuccessStatusCode) {
                return $resposta.Content.ReadAsByteArrayAsync().GetAwaiter().GetResult()
            }
        }
        finally { $resposta.Dispose() }
    }
    throw "Falha ao recuperar a imagem original."
}

function Save-Imagem([string]$Url, [string]$PastaDestino, [string]$NomeBase, [string]$Origem, [string]$Tipo) {
    $bytes = Get-BytesImagem $Url
    $extensao = Get-ExtensaoImagem $bytes
    $destino = Join-Path $PastaDestino ((Get-Slug $NomeBase) + $extensao)
    $destinoResolvido = [IO.Path]::GetFullPath($destino)
    if (-not $destinoResolvido.StartsWith($raiz, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Destino de imagem fora do projeto: $destinoResolvido"
    }
    New-Item -ItemType Directory -Path $PastaDestino -Force | Out-Null
    if (Test-Path -LiteralPath $destinoResolvido) {
        $existente = [IO.File]::ReadAllBytes($destinoResolvido)
        if ((Get-Hash $existente) -ne (Get-Hash $bytes)) {
            throw "O destino já existe com outro conteúdo: $destinoResolvido"
        }
    }
    else { [IO.File]::WriteAllBytes($destinoResolvido, $bytes) }
    $relativo = $destinoResolvido.Substring($raiz.Length).TrimStart([char[]]"\/").Replace("\", "/")
    $registros.Add([pscustomobject]@{
        tipo = $Tipo
        origem = $Origem
        url = $Url
        arquivo = $relativo
        sha256 = Get-Hash $bytes
        bytes = $bytes.Length
    })
}

try {
    Get-ChildItem -LiteralPath $pastaFichas -Recurse -File -Filter "*.md" | ForEach-Object {
        $arquivo = $_
        $grupo = $arquivo.Directory.Name
        $indice = 0
        foreach ($linha in [IO.File]::ReadAllLines($arquivo.FullName, [Text.Encoding]::UTF8)) {
            $conteudo = $linha.Trim().TrimStart("-").Trim()
            if (-not $conteudo.StartsWith("{")) { continue }
            try { $registro = $conteudo | ConvertFrom-Json }
            catch { continue }
            if (-not $registro.url -or $registro.url -notmatch "^https?://") { continue }
            $indice++
            $titulo = if ($registro.titulo) { [string]$registro.titulo } else { "aparencia-$indice" }
            $nomeBase = "{0}-{1:d2}-{2}" -f $arquivo.BaseName, $indice, $titulo
            $destino = Join-Path $pastaFichas ("imagens\" + (Get-Slug $grupo))
            try { Save-Imagem ([string]$registro.url) $destino $nomeBase $arquivo.FullName "ficha" }
            catch {
                $falhas.Add([pscustomobject]@{ tipo="ficha"; nome=$arquivo.BaseName; url=[string]$registro.url; erro=$_.Exception.Message })
            }
        }
    }

    $urlsVassouras = [ordered]@{}
    if (Test-Path -LiteralPath $arquivoImagensVassouras) {
        foreach ($linha in [IO.File]::ReadAllLines($arquivoImagensVassouras, [Text.Encoding]::UTF8)) {
            if ($linha -match "^-\s+(.+):\s+(https?://\S+)\s*$") {
                $urlsVassouras[$Matches[1].Trim()] = $Matches[2]
            }
        }
    }
    Get-ChildItem -LiteralPath $pastaVassouras -File -Filter "*.md" | ForEach-Object {
        $linhas = [IO.File]::ReadAllLines($_.FullName, [Text.Encoding]::UTF8)
        for ($i = 0; $i -lt $linhas.Length - 1; $i++) {
            if ($linhas[$i].Trim() -eq "Imagem:" -and $linhas[$i + 1].Trim() -match "^https?://") {
                $urlsVassouras[$_.BaseName] = $linhas[$i + 1].Trim()
            }
        }
    }
    $destinoVassouras = Join-Path $pastaVassouras "imagens"
    foreach ($item in $urlsVassouras.GetEnumerator()) {
        try { Save-Imagem ([string]$item.Value) $destinoVassouras ([string]$item.Key) $arquivoImagensVassouras "vassoura" }
        catch {
            $falhas.Add([pscustomobject]@{ tipo="vassoura"; nome=[string]$item.Key; url=[string]$item.Value; erro=$_.Exception.Message })
        }
    }

    New-Item -ItemType Directory -Path $pastaExportacao -Force | Out-Null
    $manifesto = Join-Path $pastaExportacao "manifesto.json"
    [IO.File]::WriteAllText(
        $manifesto,
        ($registros | ConvertTo-Json -Depth 5),
        [Text.UTF8Encoding]::new($false)
    )
    [IO.File]::WriteAllText(
        (Join-Path $pastaExportacao "falhas.json"),
        ($falhas | ConvertTo-Json -Depth 5),
        [Text.UTF8Encoding]::new($false)
    )

    if ($AplicarReferencias) {
        $porOrigem = $registros | Where-Object tipo -eq "ficha" | Group-Object origem
        foreach ($grupo in $porOrigem) {
            $linhas = [Collections.Generic.List[string]]::new()
            $linhas.AddRange([string[]][IO.File]::ReadAllLines($grupo.Name, [Text.Encoding]::UTF8))
            for ($i = 0; $i -lt $linhas.Count; $i++) {
                $conteudo = $linhas[$i].Trim().TrimStart("-").Trim()
                if (-not $conteudo.StartsWith("{")) { continue }
                try { $registro = $conteudo | ConvertFrom-Json }
                catch { continue }
                $migrado = $grupo.Group | Where-Object url -eq ([string]$registro.url) | Select-Object -First 1
                if ($null -eq $migrado) { continue }
                $novo = [ordered]@{ titulo = [string]$registro.titulo; arquivo = [string]$migrado.arquivo }
                $linhas[$i] = "- " + ($novo | ConvertTo-Json -Compress)
            }
            [IO.File]::WriteAllLines($grupo.Name, $linhas, [Text.UTF8Encoding]::new($false))
        }
        $vassouras = $registros | Where-Object tipo -eq "vassoura"
        $arquivosMarkdown = @($arquivoImagensVassouras) + @(
            Get-ChildItem -LiteralPath $pastaVassouras -File -Filter "*.md" | ForEach-Object FullName
        )
        foreach ($arquivo in $arquivosMarkdown) {
            if (-not (Test-Path -LiteralPath $arquivo)) { continue }
            $texto = [IO.File]::ReadAllText($arquivo, [Text.Encoding]::UTF8)
            foreach ($imagem in $vassouras) {
                $texto = $texto.Replace([string]$imagem.url, [string]$imagem.arquivo)
            }
            [IO.File]::WriteAllText($arquivo, $texto, [Text.UTF8Encoding]::new($false))
        }
    }

    Write-Output "IMAGENS=$($registros.Count)"
    Write-Output "FALHAS=$($falhas.Count)"
    foreach ($falha in $falhas) { Write-Output "FALHA=$($falha.tipo)|$($falha.nome)|$($falha.erro)" }
    Write-Output "MANIFESTO=$manifesto"
    Write-Output "REFERENCIAS_APLICADAS=$AplicarReferencias"
}
finally {
    $cliente.Dispose()
    $handler.Dispose()
    if ($null -ne $discordCliente) { $discordCliente.Dispose() }
}
