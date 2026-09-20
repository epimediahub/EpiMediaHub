    private fun parseManifest(json: JSONObject): AppUpdateInfo {
        val version = json.getString("version")
        val apks = json.getJSONObject("apks")
        val supported = Build.SUPPORTED_ABIS.toList()
        val abi = supported.firstOrNull { apks.has(it) } ?: "universal"
        val selected = apks.optJSONObject(abi)
            ?: apks.optJSONObject("universal")
            ?: error("Kein passendes APK im Update-Manifest.")
        val url = selected.getString("url")
        require(url.startsWith("https://download.epimediahub.com/")) {
            "Update-URL gehört nicht zur EpiMediaHub-Domain."
        }
        return AppUpdateInfo(
            version = version,
            versionCode = json.optInt("versionCode", semanticVersionCode(version)),
            url = url,
            sha256 = selected.optString("sha256").removePrefix("sha256:"),
            notes = json.optString("notes")
        )
    }

