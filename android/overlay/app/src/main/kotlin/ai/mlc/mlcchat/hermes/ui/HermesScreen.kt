package ai.mlc.mlcchat.hermes.ui

import ai.mlc.mlcchat.hermes.inference.HermesConfig
import ai.mlc.mlcchat.hermes.shizuku.ShizukuClient
import ai.mlc.mlcchat.hermes.wizard.ConfigureRemote
import ai.mlc.mlcchat.hermes.wizard.WIZARD_STEPS
import ai.mlc.mlcchat.hermes.wizard.WizardStep
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch

/**
 * Single-screen Hermes UI: wizard checklist on top, chat scrollback +
 * send field below. Once the wizard is marked complete it collapses.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HermesScreen(prefs: HermesPrefs, client: HermesClient) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()

    var wizardCollapsed by remember { mutableStateOf(prefs.wizardComplete) }
    val stepStates = remember {
        mutableStateMapOf<String, Boolean>().apply {
            WIZARD_STEPS.forEach { put(it.title, it.isComplete(ctx)) }
        }
    }
    val transcript = remember { mutableStateListOf<ChatLine>() }
    var prompt by remember { mutableStateOf("") }
    var sending by remember { mutableStateOf(false) }
    var health by remember { mutableStateOf("checking…") }

    LaunchedEffect(Unit) {
        runCatching { client.health() }.fold(
            onSuccess = { h -> health = "${h.device} • ${h.model}" },
            onFailure = { health = "daemon offline" }
        )
    }

    Scaffold(topBar = {
        TopAppBar(
            title = { Text("Hermes") },
            actions = {
                Text(health, modifier = Modifier.padding(end = 12.dp),
                    style = MaterialTheme.typography.labelSmall)
            }
        )
    }) { padding ->
        Column(
            Modifier.padding(padding).fillMaxSize().padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            if (!wizardCollapsed) {
                ElevatedCard(Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(12.dp)) {
                        Text("Setup", style = MaterialTheme.typography.titleMedium)
                        Spacer(Modifier.height(8.dp))
                        WIZARD_STEPS.forEach { step ->
                            WizardRow(step, stepStates[step.title] == true) {
                                if (step is ai.mlc.mlcchat.hermes.wizard.GrantShizuku) {
                                    scope.launch {
                                        ShizukuClient.request()
                                        stepStates[step.title] = step.isComplete(ctx)
                                    }
                                } else {
                                    step.start(ctx)
                                }
                            }
                        }
                        Spacer(Modifier.height(8.dp))
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            OutlinedButton(onClick = {
                                WIZARD_STEPS.forEach {
                                    stepStates[it.title] = it.isComplete(ctx)
                                }
                            }) { Text("Re-check") }
                            // ConfigureRemote is optional — don't block "Done" on it
                            val allDone = WIZARD_STEPS
                                .filter { it !is ConfigureRemote }
                                .all { stepStates[it.title] == true }
                            Button(
                                enabled = allDone,
                                onClick = {
                                    prefs.wizardComplete = true
                                    wizardCollapsed = true
                                }
                            ) { Text(if (allDone) "Done" else "Finish steps above") }
                        }
                    }
                }
            } else {
                AssistChip(onClick = { wizardCollapsed = false },
                    label = { Text("Setup ✓") })
            }

            val listState = rememberLazyListState()
            LazyColumn(
                state = listState,
                modifier = Modifier.weight(1f).fillMaxWidth(),
                verticalArrangement = Arrangement.spacedBy(6.dp)
            ) {
                items(transcript) { line -> ChatBubble(line) }
            }
            LaunchedEffect(transcript.size) {
                if (transcript.isNotEmpty()) listState.animateScrollToItem(transcript.lastIndex)
            }

            Row(
                Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.Bottom,
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                OutlinedTextField(
                    value = prompt,
                    onValueChange = { prompt = it },
                    modifier = Modifier.weight(1f),
                    placeholder = { Text("Ask Hermes…") },
                    singleLine = false,
                    keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
                    enabled = !sending,
                )
                Button(
                    enabled = !sending && prompt.isNotBlank(),
                    onClick = {
                        val toSend = prompt.trim()
                        prompt = ""
                        transcript += ChatLine.User(toSend)
                        sending = true
                        scope.launch {
                            val result = runCatching { client.run(toSend) }
                            sending = false
                            result.fold(
                                onSuccess = { transcript += ChatLine.Assistant(it.final ?: "[no final answer; ${it.steps} steps]") },
                                onFailure = { transcript += ChatLine.Error(it.message ?: it::class.simpleName.orEmpty()) },
                            )
                        }
                    }
                ) { Text(if (sending) "…" else "Send") }
            }
        }
    }
}

@Composable
private fun WizardRow(step: WizardStep, complete: Boolean, onClick: () -> Unit) {
    val ctx = LocalContext.current
    Row(
        Modifier.fillMaxWidth().padding(vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        Text(if (complete) "✓" else "•",
            style = MaterialTheme.typography.titleMedium)
        Column(Modifier.weight(1f)) {
            Text(step.title, style = MaterialTheme.typography.bodyMedium)
            Text(step.description, style = MaterialTheme.typography.bodySmall)

            // Inline text field for the optional G14 URL step
            if (step is ConfigureRemote && !complete) {
                var urlInput by remember { mutableStateOf(HermesConfig.load(ctx).remoteUrl) }
                OutlinedTextField(
                    value = urlInput,
                    onValueChange = { urlInput = it },
                    placeholder = { Text("http://UNIT-G14-MainNode:8765") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth().padding(top = 4.dp),
                    keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
                )
                Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    TextButton(onClick = {
                        val trimmed = urlInput.trim()
                        if (trimmed.isNotBlank()) {
                            HermesConfig.save(ctx, HermesConfig.load(ctx).copy(remoteUrl = trimmed))
                            onClick()
                        }
                    }) { Text("Save") }
                    TextButton(onClick = onClick) { Text("Skip") }
                }
            }
        }
        // "Open" button only for non-data-entry steps that aren't complete
        if (!complete && step !is ConfigureRemote) {
            TextButton(onClick = onClick) { Text("Open") }
        }
    }
}

@Composable
private fun ChatBubble(line: ChatLine) {
    val color = when (line) {
        is ChatLine.User -> MaterialTheme.colorScheme.primaryContainer
        is ChatLine.Assistant -> MaterialTheme.colorScheme.surfaceVariant
        is ChatLine.Error -> MaterialTheme.colorScheme.errorContainer
    }
    Surface(color = color, tonalElevation = 1.dp,
        modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(10.dp)) {
            Text(when (line) {
                is ChatLine.User -> "you"
                is ChatLine.Assistant -> "hermes"
                is ChatLine.Error -> "error"
            }, style = MaterialTheme.typography.labelSmall)
            Text(line.text, style = MaterialTheme.typography.bodyMedium)
        }
    }
}

sealed class ChatLine(val text: String) {
    class User(t: String) : ChatLine(t)
    class Assistant(t: String) : ChatLine(t)
    class Error(t: String) : ChatLine(t)
}
