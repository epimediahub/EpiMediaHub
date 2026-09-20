
data class PairingTicket(
    val code: String,
    val pairingSecret: String,
    val expiresAt: String
)

sealed class PairingStartResult {
    data class Success(val ticket: PairingTicket) : PairingStartResult()
    data class Error(val message: String) : PairingStartResult()
}

sealed class PairingPollResult {
    data object Pending : PairingPollResult()
    data class Connected(val payload: JSONObject) : PairingPollResult()
    data class Error(val message: String, val terminal: Boolean = false) : PairingPollResult()
}

