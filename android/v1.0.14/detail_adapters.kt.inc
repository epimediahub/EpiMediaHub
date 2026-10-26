@Composable
fun V043MediaDetailScreen(vm: MainViewModel, item: MediaEntry, accent: Color, isTv: Boolean) {
    val u by vm.ui.collectAsState()
    val context = LocalContext.current
    val detail = u.details[item.resumeKey] ?: item
    BackHandler { vm.back() }
    LaunchedEffect(item.resumeKey) { vm.ensureDetails(item) }
    Column(Modifier.fillMaxSize()) {
        EpiTopBar(if (detail.kind == MediaKind.SERIES) "SERIEN · DETAILS" else "FILME · DETAILS", R.drawable.brand_header, { vm.back() })
        V114DetailLayout(
            title = detail.name, description = detail.plot, accent = accent, isTv = isTv,
            memoryKey = "details:" + detail.resumeKey,
            metadata = listOf(detail.year, detail.duration, detail.genre, detail.rating.takeIf { it.isNotBlank() }?.let { "★ $it" }.orEmpty()),
            credits = listOf("Darsteller" to detail.cast, "Regie" to detail.director),
            loading = u.detailLoading.contains(item.resumeKey), isSeries = detail.kind == MediaKind.SERIES,
            favorite = vm.isFavorite(detail),
            poster = { modifier -> V043Poster(detail.image, detail.name, accent, modifier) },
            onPlay = { if (detail.kind == MediaKind.SERIES) vm.navigate(Screen.Episodes(detail)) else vm.play(detail) },
            onFavorite = { vm.toggleFavorite(detail) },
            onTrailer = if (detail.trailer.isBlank()) null else ({
                val raw = detail.trailer.trim()
                val url = if (raw.startsWith("http://") || raw.startsWith("https://")) raw else "https://www.youtube.com/watch?v=$raw"
                runCatching { context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url))) }
            })
        )
    }
}

@Composable
fun V043MediathekDetailScreen(vm: MainViewModel, item: MediathekClient.Item, accent: Color, isTv: Boolean) {
    var artwork by remember(item.id) { mutableStateOf(item.imageHint) }
    BackHandler { vm.back() }
    LaunchedEffect(item.id) {
        if (artwork.isBlank() && item.websiteUrl.isNotBlank()) {
            artwork = withContext(Dispatchers.IO) { MediathekClient.resolveArtwork(item) }
        }
    }
    Column(Modifier.fillMaxSize()) {
        EpiTopBar("MEDIATHEK · DETAILS", R.drawable.brand_header, { vm.back() })
        V114DetailLayout(
            title = item.media.name, description = item.description, accent = accent, isTv = isTv,
            memoryKey = "mediathek-details:" + item.id,
            metadata = listOf(item.topic, v043MediathekMeta(item)),
            credits = listOf("Quelle" to "Original-Mediathek des Senders"),
            poster = { modifier ->
                Box(modifier.clip(RoundedCornerShape(16.dp)).background(Color(0xFF101B28))) {
                    if (artwork.isNotBlank()) AsyncImage(model = artwork, contentDescription = item.media.name, modifier = Modifier.fillMaxSize(), contentScale = ContentScale.Fit)
                    else V043SenderHero(item.channel, item.topic, accent)
                }
            },
            onPlay = { vm.play(item.media) }
        )
    }
}
