package de.epimediahub.app

import de.epimediahub.app.data.MediathekClient
import de.epimediahub.app.model.MediaCategory

data object ParityMediathekHome : Screen
data class ParityMediathekDirectory(val countryId: String) : Screen
data class ParityMediathekList(val providerId: String) : Screen
data class ParityMediathekDetail(val item: MediathekClient.Item) : Screen
data class ParityEpgGrid(val category: MediaCategory) : Screen
