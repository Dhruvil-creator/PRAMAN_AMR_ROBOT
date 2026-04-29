/**
 * Autonomous Navigation Module
 * Handles A* grid visualization, mode switching, and pathfinding control
 */

class AutonomousGrid {
    constructor(canvasId, gridWidth = 20, gridHeight = 15) {
        this.canvas = document.getElementById(canvasId);
        this.ctx = this.canvas.getContext('2d');
        this.container = this.canvas.parentElement || document.body;
        
        this.gridWidth = gridWidth;
        this.gridHeight = gridHeight;
        // initialize canvas size from its container
        this.resize();
        
        this.cellWidth = this.canvas.width / (this.gridWidth || 1);
        this.cellHeight = this.canvas.height / (this.gridHeight || 1);
        
        // Grid state
        this.grid = Array(gridHeight).fill(null).map(() => Array(gridWidth).fill(0));
        this.start = null;
        this.goal = null;
        this.path = [];
        this.visitedCells = [];
        this.pathTrace = [];
        this.robotPosition = null;  // robot position [x, y]
        this.robotHeading = 0;      // heading in degrees
        
        // Tool state
        this.currentTool = null; // 'start', 'goal', 'wall', null
        
        this.setupEventListeners();
        this.draw();
    }
    
    setupEventListeners() {
        this.canvas.addEventListener('click', (e) => this.onCanvasClick(e));
        this.canvas.addEventListener('mousemove', (e) => this.onCanvasHover(e));
    }
    
    onCanvasClick(e) {
        if (!this.currentTool) return;
        
        const rect = this.canvas.getBoundingClientRect();
        const x = Math.floor((e.clientX - rect.left) / this.cellWidth);
        const y = Math.floor((e.clientY - rect.top) / this.cellHeight);
        
        // Bounds check
        if (x < 0 || x >= this.gridWidth || y < 0 || y >= this.gridHeight) return;
        
        const tool = this.currentTool;
        
        // Send to backend
        fetch('/autonomous/grid/set', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ type: tool, x, y })
        })
        .then(r => r.json())
        .then(data => {
            if (data.grid) {
                this.loadGridFromData(data.grid);
                this.draw();
            }
        })
        .catch(err => console.error('Grid set error:', err));
    }
    
    onCanvasHover(e) {
        // Could add hover preview here
        if (!this.currentTool) {
            this.canvas.style.cursor = 'default';
        } else {
            this.canvas.style.cursor = 'crosshair';
        }
    }
    
    setTool(tool) {
        this.currentTool = tool;
        
        // Visual feedback
        document.querySelectorAll('.grid-tool').forEach(btn => btn.classList.remove('active'));
        if (tool === 'start') {
            document.getElementById('gridStartBtn').classList.add('active');
        } else if (tool === 'goal') {
            document.getElementById('gridGoalBtn').classList.add('active');
        } else if (tool === 'wall') {
            document.getElementById('gridWallBtn').classList.add('active');
        }
        
        this.canvas.style.cursor = tool ? 'crosshair' : 'default';
    }
    
    loadGridFromData(gridData) {
        this.gridWidth = gridData.width;
        this.gridHeight = gridData.height;
        this.grid = gridData.grid;
        this.start = gridData.start ? { x: gridData.start[0], y: gridData.start[1] } : null;
        this.goal = gridData.goal ? { x: gridData.goal[0], y: gridData.goal[1] } : null;
        if (this.grid && (!this.start || !this.goal)) {
            for (let y = 0; y < this.gridHeight; y++) {
                for (let x = 0; x < this.gridWidth; x++) {
                    const cell = this.grid[y]?.[x];
                    if (!this.start && cell === 2) {
                        this.start = { x, y };
                    } else if (!this.goal && cell === 3) {
                        this.goal = { x, y };
                    }
                }
            }
        }
        this.cellWidth = this.canvas.width / this.gridWidth;
        this.cellHeight = this.canvas.height / this.gridHeight;
    }
    
    setPath(path, visitedCells) {
        this.path = path;
        this.visitedCells = visitedCells || [];
        this.draw();
    }

    setPathTrace(pathTrace) {
        this.pathTrace = pathTrace || [];
        this.draw();
    }
    
    setRobotPosition(position) {
        if (position) {
            this.robotPosition = position;
            this.draw();
        }
    }

    setRobotHeading(headingDeg) {
        if (Number.isFinite(headingDeg)) {
            this.robotHeading = headingDeg;
            this.draw();
        }
    }
    
    clear() {
        fetch('/autonomous/grid/clear', { method: 'POST' })
            .then(r => r.json())
            .then(data => {
                if (data.grid) {
                    this.loadGridFromData(data.grid);
                    this.path = [];
                    this.visitedCells = [];
                    this.pathTrace = [];
                    this.robotPosition = null;  // Clear robot position
                    this.currentTool = null;
                    document.querySelectorAll('.grid-tool').forEach(btn => btn.classList.remove('active'));
                    this.draw();
                }
            })
            .catch(err => console.error('Clear error:', err));
    }

    resize() {
        // Resize canvas to fit its container and recompute cell sizes
        try {
            const rect = this.container.getBoundingClientRect();
            const w = Math.max(200, Math.floor(rect.width));
            const h = Math.max(200, Math.floor(rect.height));
            this.canvas.style.width = w + 'px';
            this.canvas.style.height = h + 'px';
            this.canvas.width = w;
            this.canvas.height = h;
            this.cellWidth = this.canvas.width / Math.max(1, this.gridWidth);
            this.cellHeight = this.canvas.height / Math.max(1, this.gridHeight);
            this.draw();
        } catch (e) {
            // ignore resize errors
        }
    }
    
    draw() {
        this.ctx.fillStyle = '#0d1b2a';
        this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
        
        // Draw grid lines
        this.ctx.strokeStyle = '#1a2f3f';
        this.ctx.lineWidth = 0.5;
        for (let x = 0; x <= this.gridWidth; x++) {
            this.ctx.beginPath();
            this.ctx.moveTo(x * this.cellWidth, 0);
            this.ctx.lineTo(x * this.cellWidth, this.canvas.height);
            this.ctx.stroke();
        }
        for (let y = 0; y <= this.gridHeight; y++) {
            this.ctx.beginPath();
            this.ctx.moveTo(0, y * this.cellHeight);
            this.ctx.lineTo(this.canvas.width, y * this.cellHeight);
            this.ctx.stroke();
        }
        
        // Draw visited cells (purple)
        this.ctx.fillStyle = '#7b5ba8';
        for (const [x, y] of this.visitedCells) {
            this.ctx.fillRect(
                x * this.cellWidth + 1,
                y * this.cellHeight + 1,
                this.cellWidth - 2,
                this.cellHeight - 2
            );
        }
        
        // Draw path (blue)
        if (this.path && this.path.length > 1) {
            this.ctx.strokeStyle = 'rgba(74, 158, 255, 0.9)';
            this.ctx.lineWidth = 2;
            this.ctx.beginPath();
            this.ctx.moveTo(
                this.path[0][0] * this.cellWidth + this.cellWidth / 2,
                this.path[0][1] * this.cellHeight + this.cellHeight / 2
            );
            for (const [x, y] of this.path.slice(1)) {
                this.ctx.lineTo(
                    x * this.cellWidth + this.cellWidth / 2,
                    y * this.cellHeight + this.cellHeight / 2
                );
            }
            this.ctx.stroke();
        }
        this.ctx.fillStyle = '#4a9eff';
        for (const [x, y] of this.path) {
            this.ctx.fillRect(
                x * this.cellWidth + 2,
                y * this.cellHeight + 2,
                this.cellWidth - 4,
                this.cellHeight - 4
            );
        }

        if (this.pathTrace && this.pathTrace.length > 1) {
            this.ctx.strokeStyle = 'rgba(255, 255, 255, 0.35)';
            this.ctx.lineWidth = 1;
            this.ctx.setLineDash([4, 4]);
            this.ctx.beginPath();
            this.ctx.moveTo(
                this.pathTrace[0][0] * this.cellWidth + this.cellWidth / 2,
                this.pathTrace[0][1] * this.cellHeight + this.cellHeight / 2
            );
            for (const [x, y] of this.pathTrace.slice(1)) {
                this.ctx.lineTo(
                    x * this.cellWidth + this.cellWidth / 2,
                    y * this.cellHeight + this.cellHeight / 2
                );
            }
            this.ctx.stroke();
            this.ctx.setLineDash([]);
        }
        
        // Draw walls (gray)
        this.ctx.fillStyle = '#4a5568';
        for (let y = 0; y < this.gridHeight; y++) {
            for (let x = 0; x < this.gridWidth; x++) {
                if (this.grid[y][x] === 1) {
                    this.ctx.fillRect(
                        x * this.cellWidth + 2,
                        y * this.cellHeight + 2,
                        this.cellWidth - 4,
                        this.cellHeight - 4
                    );
                }
            }
        }

        // Draw hazards (red) and visited overlay (semi-transparent purple)
        for (let y = 0; y < this.gridHeight; y++) {
            for (let x = 0; x < this.gridWidth; x++) {
                if (this.grid[y][x] === 4) {
                    this.ctx.fillStyle = '#ff4d4f';
                    this.ctx.fillRect(
                        x * this.cellWidth + 2,
                        y * this.cellHeight + 2,
                        this.cellWidth - 4,
                        this.cellHeight - 4
                    );
                } else if (this.grid[y][x] === 5) {
                    this.ctx.fillStyle = 'rgba(123,91,168,0.6)';
                    this.ctx.fillRect(
                        x * this.cellWidth + 4,
                        y * this.cellHeight + 4,
                        this.cellWidth - 8,
                        this.cellHeight - 8
                    );
                }
            }
        }
        
        this.drawCenterOverlay();

        // Draw start (green)
        if (this.start) {
            this.ctx.fillStyle = '#48bb78';
            this.ctx.beginPath();
            this.ctx.arc(
                this.start.x * this.cellWidth + this.cellWidth / 2,
                this.start.y * this.cellHeight + this.cellHeight / 2,
                this.cellWidth / 3,
                0,
                Math.PI * 2
            );
            this.ctx.fill();
            this.ctx.fillStyle = '#0b1320';
            this.ctx.font = 'bold 11px Inter, sans-serif';
            this.ctx.textAlign = 'center';
            this.ctx.textBaseline = 'middle';
            this.ctx.fillText('S', this.start.x * this.cellWidth + this.cellWidth / 2, this.start.y * this.cellHeight + this.cellHeight / 2);
        }
        
        // Draw goal (red)
        if (this.goal) {
            this.ctx.fillStyle = '#f56565';
            this.ctx.beginPath();
            this.ctx.arc(
                this.goal.x * this.cellWidth + this.cellWidth / 2,
                this.goal.y * this.cellHeight + this.cellHeight / 2,
                this.cellWidth / 3,
                0,
                Math.PI * 2
            );
            this.ctx.fill();
            this.ctx.fillStyle = '#0b1320';
            this.ctx.font = 'bold 11px Inter, sans-serif';
            this.ctx.textAlign = 'center';
            this.ctx.textBaseline = 'middle';
            this.ctx.fillText('G', this.goal.x * this.cellWidth + this.cellWidth / 2, this.goal.y * this.cellHeight + this.cellHeight / 2);
        }
        
        // Draw robot position (cyan with outline)
        if (this.robotPosition) {
            const rx = this.robotPosition[0] * this.cellWidth + this.cellWidth / 2;
            const ry = this.robotPosition[1] * this.cellHeight + this.cellHeight / 2;
            const radius = this.cellWidth / 2.5;
            
            // Cyan circle
            this.ctx.fillStyle = '#00d4ff';
            this.ctx.beginPath();
            this.ctx.arc(rx, ry, radius, 0, Math.PI * 2);
            this.ctx.fill();
            
            // White outline
            this.ctx.strokeStyle = '#ffffff';
            this.ctx.lineWidth = 2;
            this.ctx.stroke();
            
            // Direction indicator (small triangle pointing forward)
            const headingRad = (this.robotHeading * Math.PI) / 180;
            this.ctx.save();
            this.ctx.translate(rx, ry);
            this.ctx.rotate(headingRad + Math.PI / 2);
            this.ctx.fillStyle = '#ffffff';
            this.ctx.beginPath();
            this.ctx.moveTo(0, -radius - 3);
            this.ctx.lineTo(-3, -radius / 2);
            this.ctx.lineTo(3, -radius / 2);
            this.ctx.closePath();
            this.ctx.fill();
            this.ctx.restore();
        }

        this.drawOrientationLegend();
    }

    drawCenterOverlay() {
        const cx = Math.floor(this.gridWidth / 2);
        const cy = Math.floor(this.gridHeight / 2);
        const centerX = cx * this.cellWidth + this.cellWidth / 2;
        const centerY = cy * this.cellHeight + this.cellHeight / 2;
        this.ctx.save();
        this.ctx.strokeStyle = 'rgba(80, 140, 200, 0.25)';
        this.ctx.lineWidth = 1;
        this.ctx.beginPath();
        this.ctx.moveTo(centerX, 0);
        this.ctx.lineTo(centerX, this.canvas.height);
        this.ctx.stroke();
        this.ctx.beginPath();
        this.ctx.moveTo(0, centerY);
        this.ctx.lineTo(this.canvas.width, centerY);
        this.ctx.stroke();

        const radius = Math.max(3, Math.min(this.cellWidth, this.cellHeight) / 5);
        this.ctx.fillStyle = '#f6ad55';
        this.ctx.beginPath();
        this.ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
        this.ctx.fill();
        this.ctx.strokeStyle = 'rgba(255,255,255,0.5)';
        this.ctx.stroke();

        this.ctx.fillStyle = '#fbd38d';
        this.ctx.font = '11px Inter, sans-serif';
        this.ctx.textAlign = 'left';
        this.ctx.textBaseline = 'bottom';
        this.ctx.fillText('0,0', centerX + 5, centerY - 4);
        this.ctx.restore();
    }

    drawOrientationLegend() {
        const ox = 18;
        const oy = 22;
        const len = 18;
        this.ctx.save();
        this.ctx.strokeStyle = 'rgba(200, 220, 255, 0.35)';
        this.ctx.lineWidth = 2;
        this.ctx.beginPath();
        this.ctx.moveTo(ox, oy - len);
        this.ctx.lineTo(ox, oy + len);
        this.ctx.moveTo(ox - len, oy);
        this.ctx.lineTo(ox + len, oy);
        this.ctx.stroke();

        this.ctx.fillStyle = '#cbd5e1';
        this.ctx.font = '10px Inter, sans-serif';
        this.ctx.textAlign = 'center';
        this.ctx.textBaseline = 'bottom';
        this.ctx.fillText('Front', ox, oy - len - 2);
        this.ctx.textBaseline = 'top';
        this.ctx.fillText('Back', ox, oy + len + 2);
        this.ctx.textAlign = 'right';
        this.ctx.textBaseline = 'middle';
        this.ctx.fillText('Left', ox - len - 2, oy);
        this.ctx.textAlign = 'left';
        this.ctx.fillText('Right', ox + len + 2, oy);
        this.ctx.restore();
    }
}

// ===========================
// MODE MANAGEMENT
// ===========================

let currentMode = 'manual';
let autonomousGrid = null;
let statusMonitorInterval = null;
let speedUpdateTimer = null;
let lastObstacleLogTs = 0;

function initializeAutonomous() {
    autonomousGrid = new AutonomousGrid('gridCanvas', 20, 15);
    autonomousGrid.resize();
    window.addEventListener('resize', () => autonomousGrid.resize());
    autonomousGrid.setTool('start');
    
    // Tool buttons
    document.getElementById('gridStartBtn').addEventListener('click', () => {
        autonomousGrid.setTool('start');
    });
    
    document.getElementById('gridGoalBtn').addEventListener('click', () => {
        autonomousGrid.setTool('goal');
    });
    
    document.getElementById('gridWallBtn').addEventListener('click', () => {
        autonomousGrid.setTool('wall');
    });
    
    document.getElementById('gridClearBtn').addEventListener('click', () => {
        autonomousGrid.clear();
    });
    
    // Action buttons
    document.getElementById('planPathBtn').addEventListener('click', planPath);
    document.getElementById('executePathBtn').addEventListener('click', executePath);
    document.getElementById('resumeAutoBtn').addEventListener('click', resumeAutonomous);
    document.getElementById('stopAutoBtn').addEventListener('click', stopAutonomous);
    document.getElementById('gridRecenterBtn').addEventListener('click', recenterStart);

    // Speed sliders
    const minSlider = document.getElementById('autoSpeedMin');
    const maxSlider = document.getElementById('autoSpeedMax');
    minSlider.addEventListener('input', () => updateAutoSpeed(minSlider.value, maxSlider.value));
    maxSlider.addEventListener('input', () => updateAutoSpeed(minSlider.value, maxSlider.value));

    fetch('/autonomous/speed-limits')
        .then(r => r.json())
        .then(data => {
            if (Number.isFinite(data.min_autonomous_speed)) {
                minSlider.value = data.min_autonomous_speed;
                document.getElementById('autoSpeedMinValue').textContent = data.min_autonomous_speed;
            }
            if (Number.isFinite(data.max_autonomous_speed)) {
                maxSlider.value = data.max_autonomous_speed;
                document.getElementById('autoSpeedMaxValue').textContent = data.max_autonomous_speed;
            }
        })
        .catch(() => {});
}

function startStatusMonitor() {
    // Poll autonomous status every 200ms to update UI with real-time data
    statusMonitorInterval = setInterval(() => {
        fetch('/autonomous/status')
            .then(r => r.json())
            .then(data => {
                // Prefer full grid snapshot if backend provides it, otherwise fall back to obstacles list
                if (data.grid) {
                    autonomousGrid.loadGridFromData(data.grid);
                } else if (data.obstacles && data.obstacles.length > 0) {
                    autonomousGrid.grid = Array(15).fill(null).map(() => Array(20).fill(0));
                    for (const [x, y] of data.obstacles) {
                        if (autonomousGrid.grid[y] && x < autonomousGrid.gridWidth && y < autonomousGrid.gridHeight) {
                            autonomousGrid.grid[y][x] = 1;
                        }
                    }
                }
                
                // Update path visualization
                if (data.path) {
                    autonomousGrid.setPath(data.path, []);
                }
                if (data.path_trace) {
                    autonomousGrid.setPathTrace(data.path_trace);
                }
                
                // Update robot position + heading
                if (data.robot_position) {
                    autonomousGrid.setRobotPosition(data.robot_position);
                    const posEl = document.getElementById('positionValue');
                    if (posEl) {
                        posEl.textContent = `(${data.robot_position[0].toFixed(1)}, ${data.robot_position[1].toFixed(1)})`;
                    }
                }
                if (Number.isFinite(data.robot_heading_deg)) {
                    autonomousGrid.setRobotHeading(data.robot_heading_deg);
                    const headingEl = document.getElementById('headingValue');
                    if (headingEl) {
                        headingEl.textContent = `${data.robot_heading_deg.toFixed(0)}°`;
                    }
                } else {
                    const headingEl = document.getElementById('headingValue');
                    if (headingEl) {
                        headingEl.textContent = 'N/A';
                    }
                }

                const speedEl = document.getElementById('autoSpeedValue');
                if (speedEl) {
                    speedEl.textContent = Number.isFinite(data.autonomous_speed) ? `${data.autonomous_speed}` : '-';
                }
                const obstacleEl = document.getElementById('autoObstacleValue');
                if (obstacleEl) {
                    obstacleEl.textContent = Number.isFinite(data.nearest_obstacle_cm)
                        ? `${data.nearest_obstacle_cm.toFixed(0)}cm`
                        : '-';
                }

                const statusText = data.status === 'paused' && data.pause_reason
                    ? `Status: ${data.status} (${data.pause_reason})`
                    : `Status: ${data.status}`;
                document.getElementById('planStatus').textContent =
                    `${statusText} (${data.current_waypoint}/${data.total_waypoints})`;

                const etaEl = document.getElementById('etaValue');
                if (etaEl) {
                    etaEl.textContent = formatEta(data.eta_seconds);
                }

                renderObstacleLog(data.obstacle_log || []);
                updateResumeButton(data);
                updateBadges(data);
                
                // Stop monitoring when idle
                if (data.status === 'idle' && statusMonitorInterval) {
                    clearInterval(statusMonitorInterval);
                    statusMonitorInterval = null;
                }
            })
            .catch(err => console.error('Status monitor error:', err));
    }, 200);
}

function updateAutoSpeed(minVal, maxVal) {
    const minSpeed = parseInt(minVal, 10);
    const maxSpeed = parseInt(maxVal, 10);
    document.getElementById('autoSpeedMinValue').textContent = minSpeed;
    document.getElementById('autoSpeedMaxValue').textContent = maxSpeed;

    if (speedUpdateTimer) {
        clearTimeout(speedUpdateTimer);
    }
    speedUpdateTimer = setTimeout(() => {
        fetch('/autonomous/speed-limits', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                min_autonomous_speed: minSpeed,
                max_autonomous_speed: maxSpeed
            })
        }).catch(err => console.error('Speed limits error:', err));
    }, 150);
}

function updateBadges(data) {
    const lockEl = document.getElementById('modeLockIndicator');
    const replanEl = document.getElementById('replanStatusBadge');
    if (!lockEl || !replanEl) return;

    if (data.mode === 'autonomous') {
        lockEl.textContent = 'Manual locked';
        lockEl.classList.add('locked');
    } else {
        lockEl.textContent = 'Manual enabled';
        lockEl.classList.remove('locked');
    }

    const status = (data.status || 'idle').toLowerCase();
    replanEl.textContent = status.charAt(0).toUpperCase() + status.slice(1);
    replanEl.classList.remove('executing', 'replanning');
    if (status === 'executing') {
        replanEl.classList.add('executing');
    } else if (status === 'replanning') {
        replanEl.classList.add('replanning');
    }
}

function updateResumeButton(data) {
    const resumeBtn = document.getElementById('resumeAutoBtn');
    if (!resumeBtn) return;
    const paused = data && data.paused;
    resumeBtn.disabled = !paused;
    resumeBtn.textContent = paused ? '⏵ Resume' : 'Resume';
}

function formatEta(seconds) {
    if (!Number.isFinite(seconds)) return '-';
    const sec = Math.max(0, Math.round(seconds));
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

function renderObstacleLog(logs) {
    const list = document.getElementById('obstacleLog');
    if (!list) return;
    const normalized = logs.map(item => ({
        ts: item.ts || 0,
        reason: item.reason || 'Obstacle',
        distance_cm: item.distance_cm
    })).sort((a, b) => a.ts - b.ts);

    if (normalized.length && normalized[normalized.length - 1].ts <= lastObstacleLogTs) {
        return;
    }
    list.innerHTML = '';
    normalized.slice(-8).reverse().forEach(entry => {
        const time = new Date(entry.ts * 1000).toLocaleTimeString();
        const dist = Number.isFinite(entry.distance_cm) ? ` • ${entry.distance_cm.toFixed(0)}cm` : '';
        const li = document.createElement('li');
        li.textContent = `${time} — ${entry.reason}${dist}`;
        list.appendChild(li);
    });
    if (normalized.length) {
        lastObstacleLogTs = normalized[normalized.length - 1].ts;
    }
}

function switchMode(newMode) {
    const manualControls = document.getElementById('manualControls');
    const autonomousControls = document.getElementById('autonomousControls');
    const manualBtn = document.getElementById('manualMode');
    const autoBtn = document.getElementById('autoMode');
    
    // Send mode switch to backend and trust backend as source of truth
    fetch('/mode/switch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: newMode })
    })
    .then(r => r.json())
    .then(data => {
        const appliedMode = data.mode === 'autonomous' ? 'autonomous' : 'manual';
        currentMode = appliedMode;
        if (typeof window.setMode === 'function') {
            window.setMode(appliedMode);
        }
        
        if (appliedMode === 'manual') {
            manualControls.classList.remove('hidden');
            autonomousControls.classList.add('hidden');
            manualBtn.classList.add('active');
            autoBtn.classList.remove('active');
            
            // Stop any autonomous execution
            fetch('/autonomous/stop', { method: 'POST' })
                .catch(err => console.error('Stop error:', err));
        } else {
            manualControls.classList.add('hidden');
            autonomousControls.classList.remove('hidden');
            manualBtn.classList.remove('active');
            autoBtn.classList.add('active');
        }
    })
    .catch(err => console.error('Mode switch error:', err));
}

function planPath() {
    const statusEl = document.getElementById('planStatus');
    statusEl.textContent = 'Status: Planning...';
    
    fetch('/autonomous/plan', { method: 'POST' })
        .then(r => r.json())
        .then(data => {
            if (data.status === 'success') {
                autonomousGrid.setPath(data.path, data.visited_cells);
                const pathLength = data?.stats?.path_length ?? data?.stats?.length ?? (Array.isArray(data.path) ? data.path.length : 0);
                const nodesExpanded = data?.stats?.nodes_expanded ?? '-';
                document.getElementById('pathLength').textContent = pathLength;
                document.getElementById('nodesVisited').textContent = nodesExpanded;
                statusEl.textContent = `Status: Path found (${pathLength} waypoints)`;
            } else {
                statusEl.textContent = `Status: ${data.status || 'Failed'}`;
            }
        })
        .catch(err => {
            console.error('Plan error:', err);
            statusEl.textContent = 'Status: Error';
        });
}

function executePath() {
    const statusEl = document.getElementById('planStatus');
    if (currentMode !== 'autonomous') {
        statusEl.textContent = 'Status: Switch to Autonomous first';
        return;
    }
    statusEl.textContent = 'Status: Executing...';
    
    fetch('/autonomous/execute', { method: 'POST' })
        .then(r => r.json())
        .then(data => {
            if (data.status === 'executing') {
                const total = data.total_waypoints ?? data.path_length ?? 0;
                statusEl.textContent = `Status: Executing path (${total} waypoints)`;
                // Start real-time status monitoring
                startStatusMonitor();
            } else {
                statusEl.textContent = `Status: ${data.error || data.status || 'Error'}`;
            }
        })
        .catch(err => {
            console.error('Execute error:', err);
            statusEl.textContent = 'Status: Error';
        });
}

function stopAutonomous() {
    if (statusMonitorInterval) {
        clearInterval(statusMonitorInterval);
        statusMonitorInterval = null;
    }
    
    fetch('/autonomous/stop', { method: 'POST' })
        .then(r => r.json())
        .then(data => {
            document.getElementById('planStatus').textContent = 'Status: Stopped';
        })
        .catch(err => console.error('Stop error:', err));
}

function resumeAutonomous() {
    fetch('/autonomous/resume', { method: 'POST' })
        .then(r => r.json())
        .then(data => {
            if (data.error) {
                console.error('Resume error:', data.error);
            }
        })
        .catch(err => console.error('Resume error:', err));
}

function recenterStart() {
    fetch('/autonomous/grid/recenter', { method: 'POST' })
        .then(r => r.json())
        .then(data => {
            if (data.grid) {
                autonomousGrid.loadGridFromData(data.grid);
                autonomousGrid.draw();
            }
        })
        .catch(err => console.error('Recenter error:', err));
}

// ===========================
// INITIALIZATION
// ===========================

document.addEventListener('DOMContentLoaded', () => {
    initializeAutonomous();
    
    // Mode switching
    document.getElementById('manualMode').addEventListener('click', () => switchMode('manual'));
    document.getElementById('autoMode').addEventListener('click', () => switchMode('autonomous'));

    // Sync UI with backend mode on load
    fetch('/autonomous/mode')
        .then(r => r.json())
        .then(data => {
            if (data.mode === 'autonomous') {
                switchMode('autonomous');
            } else {
                switchMode('manual');
            }
        })
        .catch(() => switchMode('manual'));

    // Open full grid page
    const openFullBtn = document.getElementById('openFullGridBtn');
    if (openFullBtn) {
        openFullBtn.addEventListener('click', () => window.open('/autonomy.html', '_blank'));
    }
});
