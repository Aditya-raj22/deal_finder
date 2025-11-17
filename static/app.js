// Deal Finder UI - Client-side JavaScript

let ws = null;
let reconnectTimer = null;

// Initialize WebSocket connection
function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;

    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        console.log('WebSocket connected');
        updateConnectionStatus(true);
        logConsole('Connected to server', 'success');
    };

    ws.onmessage = (event) => {
        const message = JSON.parse(event.data);
        handleWebSocketMessage(message);
    };

    ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        logConsole('Connection error', 'error');
    };

    ws.onclose = () => {
        console.log('WebSocket disconnected');
        updateConnectionStatus(false);
        logConsole('Disconnected from server. Reconnecting...', 'error');

        // Attempt reconnect after 3 seconds
        reconnectTimer = setTimeout(connectWebSocket, 3000);
    };
}

// Handle WebSocket messages
function handleWebSocketMessage(message) {
    switch (message.type) {
        case 'status':
            updateStatus(message.data);
            break;
        case 'pipeline_started':
            logConsole('Pipeline started with config:', 'success');
            logConsole(JSON.stringify(message.config, null, 2), 'info');
            updateButtons(true);
            break;
        case 'pipeline_stopped':
            logConsole('Pipeline stopped by user', 'info');
            updateButtons(false);
            break;
        case 'pipeline_completed':
            const exitMsg = message.exit_code === 0 ?
                'Pipeline completed successfully!' :
                `Pipeline exited with code ${message.exit_code}`;
            logConsole(exitMsg, message.exit_code === 0 ? 'success' : 'error');
            updateButtons(false);
            loadOutputs();
            break;
        case 'log':
            logConsole(message.text, message.level || 'info');
            break;
    }
}

// Update UI with status
function updateStatus(status) {
    // Update progress bar
    const progressFill = document.getElementById('progressFill');
    const progressText = document.getElementById('progressText');
    progressFill.style.width = `${status.progress}%`;
    progressText.textContent = `${status.progress}%`;

    // Update system status badge
    const systemStatus = document.getElementById('systemStatus');
    if (status.step === 'idle') {
        systemStatus.textContent = '● IDLE';
        systemStatus.className = 'status-badge';
    } else if (status.step === 'completed') {
        systemStatus.textContent = 'COMPLETED';
        systemStatus.className = 'status-badge';
    } else {
        systemStatus.textContent = `RUNNING: ${status.step.toUpperCase()}`;
        systemStatus.className = 'status-badge running';
    }

    // Update step tracker
    updateStepTracker(status);

    // Update stats
    updateStats(status.stats);

    // Estimate cost
    updateCostEstimate(status);

    // Refresh outputs if completed
    if (status.step === 'completed') {
        loadOutputs();
    }
}

// Update step tracker
function updateStepTracker(status) {
    const steps = [
        { name: 'Crawling URLs', icon: '1' },
        { name: 'Fetching Articles', icon: '2' },
        { name: 'Quick Filter (nano)', icon: '3' },
        { name: 'Deduplication', icon: '4' },
        { name: 'Extraction (gpt-4.1)', icon: '5' },
        { name: 'Parsing Results', icon: '6' }
    ];

    const stepTracker = document.getElementById('stepTracker');
    stepTracker.innerHTML = '';

    steps.forEach((step, index) => {
        const stepDiv = document.createElement('div');
        stepDiv.className = 'step';

        if (index < status.step_number - 1) {
            stepDiv.classList.add('completed');
        } else if (index === status.step_number - 1) {
            stepDiv.classList.add('active');
        }

        const icon = index < status.step_number - 1 ? '[Done]' :
                     index === status.step_number - 1 ? '[Active]' : step.icon;

        stepDiv.innerHTML = `
            <div class="step-icon">${icon}</div>
            <div class="step-name">${step.name}</div>
            <div class="step-status">${getStepStatus(index, status)}</div>
        `;

        stepTracker.appendChild(stepDiv);
    });
}

// Get step status text
function getStepStatus(index, status) {
    if (index < status.step_number - 1) return 'Complete';
    if (index === status.step_number - 1) return 'In Progress';
    return 'Pending';
}

// Update stats grid
function updateStats(stats) {
    const statsGrid = document.getElementById('statsGrid');
    statsGrid.innerHTML = '';

    for (const [key, value] of Object.entries(stats)) {
        const label = key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());

        const statCard = document.createElement('div');
        statCard.className = 'stat-card';
        statCard.innerHTML = `
            <div class="stat-label">${label}</div>
            <div class="stat-value">${value.toLocaleString()}</div>
        `;

        statsGrid.appendChild(statCard);
    }
}

// Update cost estimate
function updateCostEstimate(status) {
    // Simple estimation based on articles processed
    const articlesProcessed = status.stats.articles_fetched || 0;
    const estimatedCost = articlesProcessed * 0.02; // Rough estimate: $0.02 per article

    const costValue = document.querySelector('.cost-value');
    costValue.textContent = `$${estimatedCost.toFixed(2)}`;
}

// Add new TA text box
function addTABox() {
    const container = document.getElementById('taContainer');

    const row = document.createElement('div');
    row.className = 'ta-input-row';

    const input = document.createElement('input');
    input.type = 'text';
    input.className = 'ta-input';
    input.placeholder = 'e.g., oncology';

    const removeBtn = document.createElement('button');
    removeBtn.type = 'button';
    removeBtn.className = 'btn-inline btn-remove-ta';
    removeBtn.textContent = '−';
    removeBtn.onclick = function() { removeTABox(this); };

    row.appendChild(input);
    row.appendChild(removeBtn);
    container.appendChild(row);
}

// Remove TA text box
function removeTABox(button) {
    const container = document.getElementById('taContainer');
    const rows = container.querySelectorAll('.ta-input-row');

    // Keep at least one input
    if (rows.length <= 1) {
        logConsole('Error: At least one therapeutic area is required', 'error');
        return;
    }

    button.parentElement.remove();
}

// Start pipeline
async function startPipeline() {
    // Collect TA keywords from dynamic inputs
    const taInputs = document.querySelectorAll('.ta-input');
    const taKeywords = Array.from(taInputs)
        .map(input => input.value.trim())
        .filter(val => val.length > 0);

    const stages = Array.from(document.querySelectorAll('input[type="checkbox"][value]'))
        .filter(cb => cb.checked && !cb.classList.contains('source-checkbox'))
        .map(cb => cb.value);
    const sources = Array.from(document.querySelectorAll('.source-checkbox:checked'))
        .map(cb => cb.value);

    // Validation
    if (taKeywords.length === 0) {
        logConsole('Error: Enter at least one therapeutic area/indication', 'error');
        return;
    }
    if (stages.length === 0) {
        logConsole('Error: Select at least one development stage', 'error');
        return;
    }
    if (sources.length === 0) {
        logConsole('Error: Select at least one news source', 'error');
        return;
    }

    const config = {
        therapeutic_areas: taKeywords,
        sources: sources,
        stages: stages
    };

    try {
        const response = await fetch('/api/pipeline/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });

        if (response.ok) {
            const result = await response.json();
            logConsole(`Starting pipeline for: ${taKeywords.join(', ')}`, 'success');
            logConsole(`Stages: ${stages.join(', ')}`, 'info');
            logConsole(`Sources: ${sources.length} selected`, 'info');
            updateButtons(true);
        } else {
            const error = await response.json();
            logConsole(`Error: ${error.error}`, 'error');
        }
    } catch (error) {
        logConsole(`Failed to start pipeline: ${error.message}`, 'error');
    }
}

// Stop pipeline
async function stopPipeline() {
    try {
        const response = await fetch('/api/pipeline/stop', {
            method: 'POST'
        });

        if (response.ok) {
            logConsole('Pipeline stopped by user', 'info');
            updateButtons(false);
        } else {
            const error = await response.json();
            logConsole(`Error: ${error.error}`, 'error');
        }
    } catch (error) {
        logConsole(`Failed to stop pipeline: ${error.message}`, 'error');
    }
}

// Clear checkpoints
async function clearCheckpoints() {
    if (!confirm('Clear all checkpoints? This will start fresh on next run.')) {
        return;
    }

    try {
        const response = await fetch('/api/checkpoints', {
            method: 'DELETE'
        });

        if (response.ok) {
            const result = await response.json();
            logConsole(`Cleared ${result.cleared} checkpoint files`, 'success');
        }
    } catch (error) {
        logConsole(`Failed to clear checkpoints: ${error.message}`, 'error');
    }
}

// Load outputs
async function loadOutputs() {
    try {
        const response = await fetch('/api/outputs');
        const data = await response.json();

        const outputsList = document.getElementById('outputsList');

        if (data.files.length === 0) {
            outputsList.innerHTML = '<p class="empty-state">No outputs yet. Start a pipeline run to generate results.</p>';
            return;
        }

        outputsList.innerHTML = '';

        data.files.forEach(file => {
            const modified = new Date(file.modified);
            const sizeKB = (file.size / 1024).toFixed(2);

            const item = document.createElement('div');
            item.className = 'output-item';
            item.innerHTML = `
                <div class="output-info">
                    <div class="output-name">${file.name}</div>
                    <div class="output-meta">${modified.toLocaleString()} • ${sizeKB} KB</div>
                </div>
                <button class="output-download" onclick="downloadOutput('${file.name}')">
                    Download
                </button>
            `;

            outputsList.appendChild(item);
        });
    } catch (error) {
        logConsole(`Failed to load outputs: ${error.message}`, 'error');
    }
}

// Download output file
function downloadOutput(filename) {
    window.location.href = `/api/outputs/${filename}`;
    logConsole(`Downloading ${filename}...`, 'info');
}

// Update buttons
function updateButtons(running) {
    document.getElementById('startBtn').disabled = running;
    document.getElementById('stopBtn').disabled = !running;
}

// Log to console
function logConsole(text, level = 'info') {
    const console = document.getElementById('console');
    const line = document.createElement('div');
    line.className = `console-line console-${level}`;

    const timestamp = new Date().toLocaleTimeString();
    line.innerHTML = `
        <span class="console-prompt">[${timestamp}]</span>
        <span>${text}</span>
    `;

    console.appendChild(line);
    console.scrollTop = console.scrollHeight;

    // Keep only last 100 lines
    while (console.children.length > 100) {
        console.removeChild(console.firstChild);
    }
}

// Update connection status
function updateConnectionStatus(connected) {
    const status = document.getElementById('connectionStatus');
    status.textContent = connected ? 'Connected' : 'Disconnected';
    status.style.color = connected ? 'inherit' : '#8B1426';
}

// Initialize on page load
window.addEventListener('DOMContentLoaded', () => {
    connectWebSocket();
    loadOutputs();
    logConsole('System initialized. Ready to start pipeline.', 'success');
});

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    if (ws) {
        ws.close();
    }
    if (reconnectTimer) {
        clearTimeout(reconnectTimer);
    }
});
