
    fun savedPairing(context: Context): PairingTicket? =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getString(KEY_PAIRING, null)
            ?.let { raw ->
                runCatching {
                    val json = JSONObject(raw)
                    PairingTicket(
                        code = json.getString("code"),
                        pairingSecret = json.getString("pairing_secret"),
                        expiresAt = json.optString("expires_at")
                    )
                }.getOrNull()
            }

    fun clearPairing(context: Context) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit().remove(KEY_PAIRING).apply()
    }

    fun startPairing(context: Context): PairingStartResult {
        var conn: HttpURLConnection? = null
        return try {
            conn = connection("$PRODUCTION_BASE_URL/v1/pair/start", "POST")
            val name = listOf(Build.MANUFACTURER, Build.MODEL)
                .filter { it.isNotBlank() }
                .joinToString(" ")
                .take(80)
            val body = JSONObject()
                .put("device_id", deviceId(context))
                .put("device_name", name)
                .put("platform", "android")
            conn.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
            val status = conn.responseCode
            val text = read(conn, status)
            if (status !in 200..299) {
                PairingStartResult.Error("Kopplungsserver nicht erreichbar ($status)")
            } else {
                val json = JSONObject(text)
                val ticket = PairingTicket(
                    code = json.getString("code"),
                    pairingSecret = json.getString("pairing_secret"),
                    expiresAt = json.optString("expires_at")
                )
                context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
                    .edit()
                    .putString(
                        KEY_PAIRING,
                        JSONObject()
                            .put("code", ticket.code)
                            .put("pairing_secret", ticket.pairingSecret)
                            .put("expires_at", ticket.expiresAt)
                            .toString()
                    )
                    .commit()
                PairingStartResult.Success(ticket)
            }
        } catch (_: Exception) {
            PairingStartResult.Error("Kopplungsserver nicht erreichbar")
        } finally {
            conn?.disconnect()
        }
    }

    fun pollPairing(context: Context, ticket: PairingTicket): PairingPollResult {
        var conn: HttpURLConnection? = null
        return try {
            conn = connection("$PRODUCTION_BASE_URL/v1/pair/status", "POST")
            val body = JSONObject().put("pairing_secret", ticket.pairingSecret)
            conn.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
            val status = conn.responseCode
            val text = read(conn, status)
            when (status) {
                202 -> PairingPollResult.Pending
                in 200..299 -> {
                    val payload = JSONObject(text)
                    val config = payload.optJSONObject("config") ?: JSONObject()
                    val applyError = applyConfigToApp(context, config)
                    if (applyError != null) {
                        PairingPollResult.Error(applyError)
                    } else {
                        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
                            .edit()
                            .putString(KEY_PAYLOAD, payload.toString())
                            .putString(KEY_BASE_URL, PRODUCTION_BASE_URL)
                            .remove(KEY_PAIRING)
                            .commit()
                        DashboardSyncWorker.schedule(context.applicationContext)
                        PairingPollResult.Connected(payload)
                    }
                }
                404 -> {
                    clearPairing(context)
                    PairingPollResult.Error("Kopplung wurde nicht gefunden", terminal = true)
                }
                410 -> {
                    clearPairing(context)
                    PairingPollResult.Error("Kopplungscode ist abgelaufen", terminal = true)
                }
                else -> PairingPollResult.Error("Kopplungsserverfehler ($status)")
            }
        } catch (_: Exception) {
            PairingPollResult.Error("Kopplungsserver nicht erreichbar")
        } finally {
            conn?.disconnect()
        }
    }

