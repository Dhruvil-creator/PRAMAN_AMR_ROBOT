const state = {
    currentCommand: 'stop',
    speed: 70,
    ledOn: false,
    mode: 'manual',
    servoAngle: 75,
    metalServoEnabled: false
};

const gyroPoints = [];
const gasPoints = { mq2: [], mq135: [] };
const ultrasonicPoints = { center: [], left: [], right: [] };
const systemPoints = { cpu: [], temp: [], voltage: [] };
const timeLabels = [];

const radarCanvas = document.getElementById('radarCanvas');
const radarCtx = radarCanvas ? radarCanvas.getContext('2d') : null;
let gasChart;
let ultrasonicChart;
let gyroChart;
let systemChart;

const socket = window.io ? io('/dashboard') : null;
let socketConnected = false;

function updateFromSensorPayload(data) {
    if (!data || data.error) return;

    // Update timestamp
    document.getElementById('lastUpdate').textContent = new Date().toLocaleTimeString();

    // Update gas sensors with detailed info
    document.getElementById('mq2Value').textContent = `${data.gas.mq2.ppm} ppm`;
    document.getElementById('mq2Raw').textContent = `Raw: ${data.gas.mq2.raw}`;
    document.getElementById('mq2Voltage').textContent = `Voltage: ${data.gas.mq2.voltage?.toFixed(3) || '0.000'}V`;
    const mq2StatusEl = document.getElementById('mq2Status');
    mq2StatusEl.textContent = data.gas.mq2.status.charAt(0).toUpperCase() + data.gas.mq2.status.slice(1);
    mq2StatusEl.className = `sensor-status ${data.gas.mq2.status}`;

    document.getElementById('mq135Value').textContent = `${data.gas.mq135.ppm} ppm`;
    document.getElementById('mq135Raw').textContent = `Raw: ${data.gas.mq135.raw}`;
    document.getElementById('mq135Voltage').textContent = `Voltage: ${data.gas.mq135.voltage?.toFixed(3) || '0.000'}V`;
    const mq135StatusEl = document.getElementById('mq135Status');
    mq135StatusEl.textContent = data.gas.mq135.status.charAt(0).toUpperCase() + data.gas.mq135.status.slice(1);
    mq135StatusEl.className = `sensor-status ${data.gas.mq135.status}`;

    // Update PIR motion
    const pirValue = data.pir.alert ? 'Motion Detected' : 'Clear';
    document.getElementById('pirValue').textContent = pirValue;
    const pirIndicator = document.getElementById('pirIndicator');
    if (data.pir.alert) {
        pirIndicator.classList.add('active');
    } else {
        pirIndicator.classList.remove('active');
    }

    // Update metal detector
    const metalValue = data.metal.detected ? 'Metal Detected' : 'No Metal';
    document.getElementById('metalValue').textContent = metalValue;
    const metalIndicator = document.getElementById('metalIndicator');
    if (data.metal.detected) {
        metalIndicator.classList.add('active');
    } else {
        metalIndicator.classList.remove('active');
    }

    // Update alert cards dynamically
    const mineAlert = document.getElementById('mineAlert');
    const gasAlert = document.getElementById('gasAlert');
    const obstacleAlert = document.getElementById('obstacleAlert');
    
    if (mineAlert) {
        if (data.metal.detected) {
            mineAlert.classList.add('active');
            document.getElementById('mineAlertDetail').textContent = 'THREAT DETECTED';
        } else {
            mineAlert.classList.remove('active');
            document.getElementById('mineAlertDetail').textContent = 'No threat';
        }
    }
    
    if (gasAlert) {
        const gasRisk = data.gas.mq2.status !== 'safe' || data.gas.mq135.status !== 'safe';
        if (gasRisk) {
            gasAlert.classList.add('active');
            document.getElementById('gasAlertDetail').textContent = `MQ2: ${data.gas.mq2.ppm}ppm | MQ135: ${data.gas.mq135.ppm}ppm`;
        } else {
            gasAlert.classList.remove('active');
            document.getElementById('gasAlertDetail').textContent = 'No threat';
        }
    }
    
    if (obstacleAlert) {
        if (data.ultrasonic.status !== 'safe') {
            obstacleAlert.classList.add('active');
            document.getElementById('obstacleAlertDetail').textContent = `${data.ultrasonic.center}cm ahead`;
        } else {
            obstacleAlert.classList.remove('active');
            document.getElementById('obstacleAlertDetail').textContent = 'No threat';
        }
    }

    // Update other status
    const gyroValue = data.imu.gyro_z;
    document.getElementById('gyroStatus').textContent = gyroValue.toFixed(2);
    
    // Update gyro direction indicator
    let direction = "⊙ STABLE";
    if (gyroValue > 0.5) {
        direction = "↻ ROTATING LEFT";
    } else if (gyroValue < -0.5) {
        direction = "↺ ROTATING RIGHT";
    }
    document.getElementById('gyroDirection').textContent = direction;
    
    document.getElementById('cpuStatus').textContent = `${data.system.cpu}%`;
    document.getElementById('tempStatus').textContent = `${data.system.temp}°C`;
    document.getElementById('voltageStatus').textContent = `${data.system.voltage.toFixed(2)}V`;
    document.getElementById('batteryStatus').textContent = `Voltage ${data.system.voltage.toFixed(2)}V`;
    document.getElementById('commandStatus').textContent = state.currentCommand.toUpperCase();

    // Update alerts
    const alertBanner = document.getElementById('alertBanner');
    const topAlertStatus = document.getElementById('topAlertStatus');
    const batteryStatus = document.getElementById('batteryStatus');

    if (data.metal.detected) {
        alertBanner.textContent = '🚨 Metal detected - Potential mine hazard!';
        alertBanner.classList.add('danger');
        alertBanner.classList.remove('warning');
        topAlertStatus.textContent = 'Metal hazard detected';
        topAlertStatus.className = 'status-pill danger';
    } else if (data.pir.alert) {
        alertBanner.textContent = '⚠️ Motion detected in vicinity';
        alertBanner.classList.add('warning');
        alertBanner.classList.remove('danger');
        topAlertStatus.textContent = 'Motion detected';
        topAlertStatus.className = 'status-pill warning';
    } else if (data.gas.mq2.status !== 'safe' || data.gas.mq135.status !== 'safe') {
        alertBanner.textContent = '⚠️ Gas levels elevated - Check air quality';
        alertBanner.classList.add('warning');
        alertBanner.classList.remove('danger');
        topAlertStatus.textContent = 'Gas threshold exceeded';
        topAlertStatus.className = 'status-pill warning';
    } else if (data.ultrasonic.status !== 'safe') {
        alertBanner.textContent = '⚠️ Obstacle detected ahead';
        alertBanner.classList.add('warning');
        alertBanner.classList.remove('danger');
        topAlertStatus.textContent = 'Obstacle detected';
        topAlertStatus.className = 'status-pill caution';
    } else {
        alertBanner.textContent = '✅ All systems nominal - Safe to proceed';
        alertBanner.classList.remove('warning', 'danger');
        topAlertStatus.textContent = 'All systems nominal';
        topAlertStatus.className = 'status-pill';
    }

    if (batteryStatus) {
        batteryStatus.className = 'status-pill battery';
    }

    drawRadar(data.ultrasonic);

    // Update chart data
    const label = new Date().toLocaleTimeString();
    timeLabels.push(label);

    gasPoints.mq2.push(data.gas.mq2.ppm);
    gasPoints.mq135.push(data.gas.mq135.ppm);
    ultrasonicPoints.center.push(data.ultrasonic.center);
    ultrasonicPoints.left.push(data.ultrasonic.left);
    ultrasonicPoints.right.push(data.ultrasonic.right);
    gyroPoints.push(data.imu.gyro_z);
    systemPoints.cpu.push(data.system.cpu);
    systemPoints.temp.push(data.system.temp);
    systemPoints.voltage.push(data.system.voltage);

    if (timeLabels.length > 25) {
        timeLabels.shift();
        gasPoints.mq2.shift();
        gasPoints.mq135.shift();
        ultrasonicPoints.center.shift();
        ultrasonicPoints.left.shift();
        ultrasonicPoints.right.shift();
        gyroPoints.shift();
        systemPoints.cpu.shift();
        systemPoints.temp.shift();
        systemPoints.voltage.shift();
    }

    // Update charts
    gasChart.data.labels = [...timeLabels];
    gasChart.data.datasets[0].data = [...gasPoints.mq2];
    gasChart.data.datasets[1].data = [...gasPoints.mq135];
    gasChart.update();

    ultrasonicChart.data.labels = [...timeLabels];
    ultrasonicChart.data.datasets[0].data = [...ultrasonicPoints.center];
    ultrasonicChart.data.datasets[1].data = [...ultrasonicPoints.left];
    ultrasonicChart.data.datasets[2].data = [...ultrasonicPoints.right];
    ultrasonicChart.update();

    gyroChart.data.labels = [...timeLabels];
    gyroChart.data.datasets[0].data = [...gyroPoints];
    gyroChart.update();

    systemChart.data.labels = [...timeLabels];
    systemChart.data.datasets[0].data = [...systemPoints.cpu];
    systemChart.data.datasets[1].data = [...systemPoints.temp];
    systemChart.data.datasets[2].data = [...systemPoints.voltage];
    systemChart.update();
}

function sendCommand(command) {
    if (state.mode === 'autonomous' && command !== 'stop') {
        console.warn('Manual control blocked while in autonomous mode');
        return;
    }

    state.currentCommand = command;

    if (socketConnected && socket) {
        socket.emit('control_command', { command, speed: state.speed });
        return;
    }

    fetch('/control', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: `command=${command}`
    });
}

function emergencyStop() {
    state.currentCommand = 'stop';

    if (socketConnected && socket) {
        socket.emit('control_command', { command: 'stop' });
        return;
    }

    fetch('/emergency');
}

function updateSpeed(value) {
    state.speed = value;
    document.getElementById('speedValue').textContent = value;
    document.getElementById('speedStatus').textContent = `${value}%`;

    if (socketConnected && socket) {
        socket.emit('control_command', { speed: value });
        return;
    }

    fetch('/speed', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: `speed=${value}`
    });
}

function toggleLed() {
    state.ledOn = !state.ledOn;
    document.getElementById('ledToggle').textContent = state.ledOn ? 'LED OFF' : 'LED ON';
    // Placeholder for actual LED API
}

function servoAction() {
    state.servoAngle = 120;
    document.getElementById('servoStatus').textContent = '120°';
    fetch('/servo', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: 'action=action'
    }).catch(err => console.error('Servo action error:', err));
}

function servoRestore() {
    state.servoAngle = 75;
    document.getElementById('servoStatus').textContent = '75°';
    fetch('/servo', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: 'action=restore'
    }).catch(err => console.error('Servo restore error:', err));
}

function toggleMetalDetection() {
    fetch('/servo', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: 'action=metal_detect_toggle'
    })
    .then(res => res.json())
    .then(data => {
        state.metalServoEnabled = data.metal_servo;
        const btn = document.getElementById('metalToggle');
        if (btn) {
            btn.classList.toggle('active', state.metalServoEnabled);
            btn.textContent = state.metalServoEnabled ? '🔴 Metal Detection ON' : '🟢 Metal Detection OFF';
        }
    })
    .catch(err => console.error('Metal toggle error:', err));
}

function setMode(mode) {
    state.mode = mode;
    document.getElementById('manualMode').classList.toggle('active', mode === 'manual');
    document.getElementById('autoMode').classList.toggle('active', mode === 'autonomous');
    const manualControls = document.getElementById('manualControls');
    const autonomousControls = document.getElementById('autonomousControls');
    if (manualControls && autonomousControls) {
        manualControls.classList.toggle('hidden', mode !== 'manual');
        autonomousControls.classList.toggle('hidden', mode !== 'autonomous');
    }
}

function getColor(distance) {
    if (distance < 20) return 'red';
    if (distance < 50) return 'yellow';
    return 'lime';
}

function drawRadar(data) {
    if (!radarCtx) return;
    const w = radarCanvas.width;
    const h = radarCanvas.height;
    radarCtx.clearRect(0, 0, w, h);

    const centerX = w / 2;
    const centerY = h / 2;
    const maxDistance = 150; // Max display distance in cm

    // Draw concentric circles
    radarCtx.strokeStyle = 'rgba(255,255,255,0.1)';
    radarCtx.lineWidth = 1;
    for (let r = 50; r <= maxDistance; r += 50) {
        const radius = (r / maxDistance) * 120;
        radarCtx.beginPath();
        radarCtx.arc(centerX, centerY, radius, 0, Math.PI * 2);
        radarCtx.stroke();
    }

    // Draw center dot
    radarCtx.fillStyle = '#ffffff';
    radarCtx.beginPath();
    radarCtx.arc(centerX, centerY, 4, 0, Math.PI * 2);
    radarCtx.fill();

    // Draw sensor rays
    const rays = [
        { angle: 0, value: Math.min(data.center, maxDistance), label: 'Center' },
        { angle: -45, value: Math.min(data.left, maxDistance), label: 'Left' },
        { angle: 45, value: Math.min(data.right, maxDistance), label: 'Right' }
    ];

    rays.forEach(ray => {
        const length = (ray.value / maxDistance) * 120;
        const rad = (ray.angle * Math.PI) / 180;
        const x = centerX + length * Math.sin(rad);
        const y = centerY - length * Math.cos(rad);

        // Determine color based on distance
        let color = 'lime'; // Safe
        if (ray.value < 20) color = 'red'; // Danger
        else if (ray.value < 50) color = 'yellow'; // Near

        radarCtx.strokeStyle = color;
        radarCtx.lineWidth = 3;
        radarCtx.beginPath();
        radarCtx.moveTo(centerX, centerY);
        radarCtx.lineTo(x, y);
        radarCtx.stroke();

        // Draw endpoint dot
        radarCtx.fillStyle = color;
        radarCtx.beginPath();
        radarCtx.arc(x, y, 3, 0, Math.PI * 2);
        radarCtx.fill();

        // Draw distance label
        radarCtx.fillStyle = '#ffffff';
        radarCtx.font = '10px Arial';
        radarCtx.textAlign = 'center';
        const labelX = centerX + (length + 15) * Math.sin(rad);
        const labelY = centerY - (length + 15) * Math.cos(rad);
        radarCtx.fillText(`${ray.value}cm`, labelX, labelY);
    });

    // Draw direction labels
    radarCtx.fillStyle = '#8ea0b8';
    radarCtx.font = '12px Arial';
    radarCtx.textAlign = 'center';
    radarCtx.fillText('Front', centerX, centerY - 130);
}

async function refreshData() {
    try {
        const res = await fetch('/sensor-data');
        const data = await res.json();
        updateFromSensorPayload(data);
        updateConnectionStatus(true);
    } catch (error) {
        console.error('Data refresh error', error);
        updateConnectionStatus(false);
    }
}

function updateConnectionStatus(connected) {
    const indicator = document.getElementById('connectionStatus');
    const dot = indicator.querySelector('.status-dot');
    const text = document.getElementById('connectionText');

    if (connected) {
        dot.className = 'status-dot status-ok';
        text.textContent = 'Connected';
    } else {
        dot.className = 'status-dot status-error';
        text.textContent = 'Disconnected';
    }
}

function createCharts() {
    const gasCtx = document.getElementById('gasChart').getContext('2d');
    const ultrasonicCtx = document.getElementById('ultrasonicChart').getContext('2d');
    const gyroCtx = document.getElementById('gyroChart').getContext('2d');
    const systemCtx = document.getElementById('systemChart').getContext('2d');

    gasChart = new Chart(gasCtx, {
        type: 'line',
        data: {
            labels: timeLabels,
            datasets: [
                {
                    label: 'MQ2 (LPG/Smoke)',
                    borderColor: '#4ade80',
                    backgroundColor: 'rgba(74, 222, 128, 0.1)',
                    data: gasPoints.mq2,
                    tension: 0.4,
                    pointRadius: 2
                },
                {
                    label: 'MQ135 (Air Quality)',
                    borderColor: '#60a5fa',
                    backgroundColor: 'rgba(96, 165, 250, 0.1)',
                    data: gasPoints.mq135,
                    tension: 0.4,
                    pointRadius: 2
                }
            ]
        },
        options: {
            responsive: true,
            animation: false,
            plugins: {
                legend: { display: true, position: 'top' }
            },
            scales: {
                y: { beginAtZero: true, title: { display: true, text: 'PPM' } }
            }
        }
    });

    ultrasonicChart = new Chart(ultrasonicCtx, {
        type: 'line',
        data: {
            labels: timeLabels,
            datasets: [
                {
                    label: 'Center',
                    borderColor: '#fbbf24',
                    backgroundColor: 'rgba(251, 191, 36, 0.1)',
                    data: ultrasonicPoints.center,
                    tension: 0.4,
                    pointRadius: 2
                },
                {
                    label: 'Left',
                    borderColor: '#f87171',
                    backgroundColor: 'rgba(248, 113, 113, 0.1)',
                    data: ultrasonicPoints.left,
                    tension: 0.4,
                    pointRadius: 2
                },
                {
                    label: 'Right',
                    borderColor: '#a78bfa',
                    backgroundColor: 'rgba(167, 139, 250, 0.1)',
                    data: ultrasonicPoints.right,
                    tension: 0.4,
                    pointRadius: 2
                }
            ]
        },
        options: {
            responsive: true,
            animation: false,
            plugins: {
                legend: { display: true, position: 'top' }
            },
            scales: {
                y: { beginAtZero: true, title: { display: true, text: 'Distance (cm)' } }
            }
        }
    });

    gyroChart = new Chart(gyroCtx, {
        type: 'line',
        data: {
            labels: timeLabels,
            datasets: [{
                label: 'Gyro Z',
                borderColor: '#ec4899',
                backgroundColor: 'rgba(236, 72, 153, 0.1)',
                data: gyroPoints,
                tension: 0.4,
                pointRadius: 2
            }]
        },
        options: {
            responsive: true,
            animation: false,
            plugins: {
                legend: { display: true, position: 'top' }
            },
            scales: {
                y: { title: { display: true, text: '°/s' } }
            }
        }
    });

    systemChart = new Chart(systemCtx, {
        type: 'line',
        data: {
            labels: timeLabels,
            datasets: [
                {
                    label: 'CPU %',
                    borderColor: '#10b981',
                    backgroundColor: 'rgba(16, 185, 129, 0.1)',
                    data: systemPoints.cpu,
                    tension: 0.4,
                    pointRadius: 2,
                    yAxisID: 'y'
                },
                {
                    label: 'Temperature °C',
                    borderColor: '#f59e0b',
                    backgroundColor: 'rgba(245, 158, 11, 0.1)',
                    data: systemPoints.temp,
                    tension: 0.4,
                    pointRadius: 2,
                    yAxisID: 'y1'
                },
                {
                    label: 'Voltage V',
                    borderColor: '#8b5cf6',
                    backgroundColor: 'rgba(139, 92, 246, 0.1)',
                    data: systemPoints.voltage,
                    tension: 0.4,
                    pointRadius: 2,
                    yAxisID: 'y2'
                }
            ]
        },
        options: {
            responsive: true,
            animation: false,
            plugins: {
                legend: { display: true, position: 'top' }
            },
            scales: {
                y: {
                    type: 'linear',
                    display: true,
                    position: 'left',
                    title: { display: true, text: 'CPU %' }
                },
                y1: {
                    type: 'linear',
                    display: true,
                    position: 'right',
                    title: { display: true, text: 'Temp °C' },
                    grid: { drawOnChartArea: false }
                },
                y2: {
                    type: 'linear',
                    display: false // Hide voltage scale to avoid clutter
                }
            }
        }
    });
}

function addEventListeners() {
    // Direction buttons: press to move, release to stop
    document.getElementById('forwardBtn').addEventListener('mousedown', () => sendCommand('forward'));
    document.getElementById('forwardBtn').addEventListener('mouseup', () => sendCommand('stop'));
    document.getElementById('forwardBtn').addEventListener('mouseleave', () => sendCommand('stop'));
    
    document.getElementById('leftBtn').addEventListener('mousedown', () => sendCommand('left'));
    document.getElementById('leftBtn').addEventListener('mouseup', () => sendCommand('stop'));
    document.getElementById('leftBtn').addEventListener('mouseleave', () => sendCommand('stop'));
    
    document.getElementById('rightBtn').addEventListener('mousedown', () => sendCommand('right'));
    document.getElementById('rightBtn').addEventListener('mouseup', () => sendCommand('stop'));
    document.getElementById('rightBtn').addEventListener('mouseleave', () => sendCommand('stop'));
    
    document.getElementById('backwardBtn').addEventListener('mousedown', () => sendCommand('backward'));
    document.getElementById('backwardBtn').addEventListener('mouseup', () => sendCommand('stop'));
    document.getElementById('backwardBtn').addEventListener('mouseleave', () => sendCommand('stop'));
    
    document.getElementById('stopBtn').addEventListener('click', () => sendCommand('stop'));
    document.getElementById('emergencyBtn').addEventListener('click', emergencyStop);
    document.getElementById('servoOpen').addEventListener('click', servoAction);
    document.getElementById('servoClose').addEventListener('click', servoRestore);
    document.getElementById('ledToggle').addEventListener('click', toggleLed);
    document.getElementById('speedRange').addEventListener('input', event => updateSpeed(event.target.value));
    document.getElementById('manualMode').addEventListener('click', () => setMode('manual'));
    document.getElementById('autoMode').addEventListener('click', () => setMode('autonomous'));
    
    // Metal detection toggle
    const metalToggleBtn = document.getElementById('metalToggle');
    if (metalToggleBtn) {
        metalToggleBtn.addEventListener('click', toggleMetalDetection);
    }
    
    const cameraRefreshBtn = document.querySelector('.camera-refresh');
    if (cameraRefreshBtn) {
        cameraRefreshBtn.addEventListener('click', refreshCameraFeed);
    }
    const cameraImg = document.getElementById('cameraFeed');
    if (cameraImg) {
        cameraImg.addEventListener('error', () => {
            cameraImg.alt = 'Camera stream unavailable';
            cameraImg.classList.add('camera-error');
        });
    }
}

function refreshCameraFeed() {
    const img = document.getElementById('cameraFeed');
    if (!img) return;
    img.classList.remove('camera-error');
    img.alt = 'Live camera feed';
    img.src = `/camera_feed?ts=${Date.now()}`;
}

window.addEventListener('DOMContentLoaded', () => {
    // Initialize servo to 75° center position
    document.getElementById('servoStatus').textContent = '75°';
    
    createCharts();
    addEventListeners();

    if (socket) {
        socket.on('connect', () => {
            socketConnected = true;
            console.log('Socket connected');
            document.getElementById('connectionText').textContent = 'Connected';
            document.querySelector('.status-dot').className = 'status-dot status-ok';
        });

        socket.on('disconnect', () => {
            socketConnected = false;
            console.log('Socket disconnected');
            document.getElementById('connectionText').textContent = 'Disconnected';
            document.querySelector('.status-dot').className = 'status-dot status-error';
        });

        socket.on('sensor_update', data => {
            updateFromSensorPayload(data);
        });

        socket.on('control_ack', data => {
            if (data.command) {
                state.currentCommand = data.command;
                document.getElementById('commandStatus').textContent = data.command.toUpperCase();
            }
            if (typeof data.speed === 'number') {
                state.speed = data.speed;
                document.getElementById('speedValue').textContent = data.speed;
                document.getElementById('speedStatus').textContent = `${data.speed}%`;
                document.getElementById('speedRange').value = data.speed;
            }
        });
    }
    
    // Load system status to get metal_servo_enabled state
    fetch('/status')
        .then(res => res.json())
        .then(data => {
            if (data.mode === 'autonomous' || data.mode === 'manual') {
                setMode(data.mode);
            }
            state.metalServoEnabled = data.metal_servo_enabled || false;
            const btn = document.getElementById('metalToggle');
            if (btn) {
                btn.classList.toggle('active', state.metalServoEnabled);
                btn.textContent = state.metalServoEnabled ? '🔴 Metal Detection ON' : '🟢 Metal Detection OFF';
            }
        })
        .catch(err => console.error('Failed to load status:', err));

    refreshData();
    setInterval(refreshData, 2000);
});
