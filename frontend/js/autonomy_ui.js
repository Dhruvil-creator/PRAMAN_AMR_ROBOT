/* Minimal autonomous full-page UI script
   - Responsive full canvas grid
   - Basic start/goal/wall placement
   - Plan / Execute controls via existing backend endpoints
*/

class AutonomousGridFull {
    constructor(canvasId) {
        this.canvas = document.getElementById(canvasId);
        this.ctx = this.canvas.getContext('2d');
        this.container = this.canvas.parentElement || document.body;
        this.gridWidth = 20;
        this.gridHeight = 15;
        this.grid = [];
        this.start = null;
        this.goal = null;
        this.path = [];
        this.pathTrace = [];
        this.visited = [];
        this.tool = null;
        this.robotPosition = null;
        this.robotHeading = 0;
        this.hasAutoRecentered = false;

        this.resize();
        this.setupListeners();
        this.setTool('start');
        this.pollStatus();
    }

    resize() {
        const rect = this.container.getBoundingClientRect();
        const w = Math.max(200, Math.floor(rect.width));
        const h = Math.max(200, Math.floor(rect.height));
        this.canvas.style.width = w + 'px';
        this.canvas.style.height = h + 'px';
        this.canvas.width = w;
        this.canvas.height = h;
        this.cellW = this.canvas.width / Math.max(1, this.gridWidth);
        this.cellH = this.canvas.height / Math.max(1, this.gridHeight);
        this.draw();
    }

    setupListeners() {
        window.addEventListener('resize', () => this.resize());
        this.canvas.addEventListener('click', (e) => this.onClick(e));

        // buttons
        const mapBtn = id => document.getElementById(id);
        const startBtn = mapBtn('gridStartBtn');
        const goalBtn = mapBtn('gridGoalBtn');
        const wallBtn = mapBtn('gridWallBtn');
        const clearBtn = mapBtn('gridClearBtn');
        const recenterBtn = mapBtn('gridRecenterBtn');
        const planBtn = mapBtn('planPathBtn');
        const execBtn = mapBtn('executePathBtn');

        if (startBtn) startBtn.addEventListener('click', () => this.setTool('start'));
        if (goalBtn) goalBtn.addEventListener('click', () => this.setTool('goal'));
        if (wallBtn) wallBtn.addEventListener('click', () => this.setTool('wall'));
        if (clearBtn) clearBtn.addEventListener('click', () => this.clearGrid());
        if (recenterBtn) recenterBtn.addEventListener('click', () => this.recenterStart());
        if (planBtn) planBtn.addEventListener('click', () => this.planPath());
        if (execBtn) execBtn.addEventListener('click', () => this.executePath());

        const backBtn = document.getElementById('openDashboardBtn');
        if (backBtn) backBtn.addEventListener('click', () => window.location.href = '/');
    }

    setTool(t) {
        this.tool = t;
        document.querySelectorAll('.grid-tool').forEach(btn => btn.classList.remove('active'));
        if (t === 'start') {
            document.getElementById('gridStartBtn')?.classList.add('active');
        } else if (t === 'goal') {
            document.getElementById('gridGoalBtn')?.classList.add('active');
        } else if (t === 'wall') {
            document.getElementById('gridWallBtn')?.classList.add('active');
        }
        const toolStatus = document.getElementById('toolStatus');
        if (toolStatus) {
            toolStatus.textContent = `Tool: ${t ? t[0].toUpperCase() + t.slice(1) : '-'}`;
        }
        if (this.canvas) {
            this.canvas.style.cursor = t ? 'crosshair' : 'default';
        }
    }

    onClick(e) {
        if (!this.tool) return;
        const rect = this.canvas.getBoundingClientRect();
        const x = Math.floor((e.clientX - rect.left) / this.cellW);
        const y = Math.floor((e.clientY - rect.top) / this.cellH);
        if (x < 0 || y < 0 || x >= this.gridWidth || y >= this.gridHeight) return;

        fetch('/autonomous/grid/set', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ type: this.tool, x: x, y: y, grid: 'controller' })
        }).then(r => r.json()).then(data => {
            if (data.grid) {
                this.loadGridFromData(data.grid);
            }
            const status = document.getElementById('planStatus');
            if (status) {
                status.textContent = `Status: ${this.tool} set (${x}, ${y})`;
            }
        }).catch(err => console.error('grid set error', err));
    }

    loadGridFromData(gd) {
        if (!gd) return;
        this.gridWidth = gd.width || this.gridWidth;
        this.gridHeight = gd.height || this.gridHeight;
        this.grid = gd.grid || [];
        this.start = gd.start ? {x: gd.start[0], y: gd.start[1]} : null;
        this.goal = gd.goal ? {x: gd.goal[0], y: gd.goal[1]} : null;
        if (this.grid && (!this.start || !this.goal)) {
            for (let y = 0; y < this.gridHeight; y++) {
                for (let x = 0; x < this.gridWidth; x++) {
                    const cell = this.grid[y]?.[x];
                    if (!this.start && cell === 2) {
                        this.start = {x, y};
                    } else if (!this.goal && cell === 3) {
                        this.goal = {x, y};
                    }
                }
            }
        }
        this.cellW = this.canvas.width / Math.max(1, this.gridWidth);
        this.cellH = this.canvas.height / Math.max(1, this.gridHeight);
        this.updateGridMeta();
        this.draw();
    }

    updateGridMeta() {
        const meta = document.getElementById('gridMeta');
        if (!meta) return;
        const cx = Math.floor(this.gridWidth / 2);
        const cy = Math.floor(this.gridHeight / 2);
        const startTxt = this.start ? `S(${this.start.x},${this.start.y})` : 'S(-,-)';
        const goalTxt = this.goal ? `G(${this.goal.x},${this.goal.y})` : 'G(-,-)';
        meta.textContent = `Center: (${cx},${cy}) • ${startTxt} • ${goalTxt}`;
    }

    draw() {
        if (!this.ctx) return;
        this.ctx.fillStyle = '#0d1b2a';
        this.ctx.fillRect(0,0,this.canvas.width,this.canvas.height);
        this.ctx.strokeStyle = '#1a2f3f';
        this.ctx.lineWidth = 0.5;

        for (let x=0;x<=this.gridWidth;x++){
            this.ctx.beginPath();
            this.ctx.moveTo(x*this.cellW,0);
            this.ctx.lineTo(x*this.cellW,this.canvas.height);
            this.ctx.stroke();
        }
        for (let y=0;y<=this.gridHeight;y++){
            this.ctx.beginPath();
            this.ctx.moveTo(0,y*this.cellH);
            this.ctx.lineTo(this.canvas.width,y*this.cellH);
            this.ctx.stroke();
        }

        // draw walls
        this.ctx.fillStyle = '#4a5568';
        for (let y=0;y<this.gridHeight;y++){
            for (let x=0;x<this.gridWidth;x++){
                if (this.grid && this.grid[y] && this.grid[y][x]===1){
                    this.ctx.fillRect(x*this.cellW+1,y*this.cellH+1,this.cellW-2,this.cellH-2);
                }
            }
        }

        // draw hazards (danger)
        for (let y=0;y<this.gridHeight;y++){
            for (let x=0;x<this.gridWidth;x++){
                if (this.grid && this.grid[y] && this.grid[y][x]===4){
                    this.ctx.fillStyle = '#ff4d4f';
                    this.ctx.fillRect(x*this.cellW+2,y*this.cellH+2,this.cellW-4,this.cellH-4);
                }
            }
        }

        // draw visited trace
        for (let y=0;y<this.gridHeight;y++){
            for (let x=0;x<this.gridWidth;x++){
                if (this.grid && this.grid[y] && this.grid[y][x]===5){
                    this.ctx.fillStyle = 'rgba(123,91,168,0.6)';
                    this.ctx.fillRect(x*this.cellW+4,y*this.cellH+4,this.cellW-8,this.cellH-8);
                }
            }
        }

        // draw path
        if (this.path && this.path.length > 1) {
            this.ctx.strokeStyle = 'rgba(74, 158, 255, 0.9)';
            this.ctx.lineWidth = 2;
            this.ctx.beginPath();
            this.ctx.moveTo(this.path[0][0]*this.cellW+this.cellW/2, this.path[0][1]*this.cellH+this.cellH/2);
            for (const p of this.path.slice(1)) {
                this.ctx.lineTo(p[0]*this.cellW+this.cellW/2, p[1]*this.cellH+this.cellH/2);
            }
            this.ctx.stroke();
        }
        this.ctx.fillStyle = '#4a9eff';
        for (const p of this.path) {
            this.ctx.fillRect(p[0]*this.cellW+2,p[1]*this.cellH+2,this.cellW-4,this.cellH-4);
        }

        if (this.pathTrace && this.pathTrace.length > 1) {
            this.ctx.strokeStyle = 'rgba(255, 255, 255, 0.35)';
            this.ctx.lineWidth = 1;
            this.ctx.setLineDash([4, 4]);
            this.ctx.beginPath();
            this.ctx.moveTo(this.pathTrace[0][0]*this.cellW+this.cellW/2, this.pathTrace[0][1]*this.cellH+this.cellH/2);
            for (const t of this.pathTrace.slice(1)) {
                this.ctx.lineTo(t[0]*this.cellW+this.cellW/2, t[1]*this.cellH+this.cellH/2);
            }
            this.ctx.stroke();
            this.ctx.setLineDash([]);
        }

        this.drawCenterOverlay();

        // start / goal
        if (this.start) {
            this.ctx.fillStyle = '#48bb78';
            this.ctx.beginPath();
            this.ctx.arc(this.start.x*this.cellW+this.cellW/2,this.start.y*this.cellH+this.cellH/2,Math.min(this.cellW,this.cellH)/3,0,Math.PI*2);
            this.ctx.fill();
            this.ctx.fillStyle = '#0b1320';
            this.ctx.font = 'bold 12px Inter, sans-serif';
            this.ctx.textAlign = 'center';
            this.ctx.textBaseline = 'middle';
            this.ctx.fillText('S', this.start.x*this.cellW+this.cellW/2, this.start.y*this.cellH+this.cellH/2);
        }
        if (this.goal) {
            this.ctx.fillStyle = '#f56565';
            this.ctx.beginPath();
            this.ctx.arc(this.goal.x*this.cellW+this.cellW/2,this.goal.y*this.cellH+this.cellH/2,Math.min(this.cellW,this.cellH)/3,0,Math.PI*2);
            this.ctx.fill();
            this.ctx.fillStyle = '#0b1320';
            this.ctx.font = 'bold 12px Inter, sans-serif';
            this.ctx.textAlign = 'center';
            this.ctx.textBaseline = 'middle';
            this.ctx.fillText('G', this.goal.x*this.cellW+this.cellW/2, this.goal.y*this.cellH+this.cellH/2);
        }

        // robot position + heading
        if (this.robotPosition) {
            const rx = this.robotPosition[0] * this.cellW + this.cellW / 2;
            const ry = this.robotPosition[1] * this.cellH + this.cellH / 2;
            const radius = Math.min(this.cellW, this.cellH) / 2.4;
            this.ctx.fillStyle = '#00d4ff';
            this.ctx.beginPath();
            this.ctx.arc(rx, ry, radius, 0, Math.PI * 2);
            this.ctx.fill();
            this.ctx.strokeStyle = '#ffffff';
            this.ctx.lineWidth = 2;
            this.ctx.stroke();

            const headingRad = (this.robotHeading * Math.PI) / 180;
            this.ctx.save();
            this.ctx.translate(rx, ry);
            this.ctx.rotate(headingRad + Math.PI / 2);
            this.ctx.fillStyle = '#ffffff';
            this.ctx.beginPath();
            this.ctx.moveTo(0, -radius - 3);
            this.ctx.lineTo(-4, -radius / 2);
            this.ctx.lineTo(4, -radius / 2);
            this.ctx.closePath();
            this.ctx.fill();
            this.ctx.restore();
        }

        this.drawOrientationLegend();
    }

    drawCenterOverlay() {
        const cx = Math.floor(this.gridWidth / 2);
        const cy = Math.floor(this.gridHeight / 2);
        const centerX = cx * this.cellW + this.cellW / 2;
        const centerY = cy * this.cellH + this.cellH / 2;
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

        const radius = Math.max(3, Math.min(this.cellW, this.cellH) / 5);
        this.ctx.fillStyle = '#f6ad55';
        this.ctx.beginPath();
        this.ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
        this.ctx.fill();
        this.ctx.strokeStyle = 'rgba(255,255,255,0.5)';
        this.ctx.stroke();

        this.ctx.fillStyle = '#fbd38d';
        this.ctx.font = '12px Inter, sans-serif';
        this.ctx.textAlign = 'left';
        this.ctx.textBaseline = 'bottom';
        this.ctx.fillText('0,0', centerX + 6, centerY - 4);
        this.ctx.restore();
    }

    drawOrientationLegend() {
        const ox = 22;
        const oy = 26;
        const len = 22;
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
        this.ctx.font = '11px Inter, sans-serif';
        this.ctx.textAlign = 'center';
        this.ctx.textBaseline = 'bottom';
        this.ctx.fillText('Front', ox, oy - len - 4);
        this.ctx.textBaseline = 'top';
        this.ctx.fillText('Back', ox, oy + len + 2);
        this.ctx.textAlign = 'right';
        this.ctx.textBaseline = 'middle';
        this.ctx.fillText('Left', ox - len - 4, oy);
        this.ctx.textAlign = 'left';
        this.ctx.fillText('Right', ox + len + 4, oy);
        this.ctx.restore();
    }

    pollStatus() {
        // poll once per 250ms
        setInterval(()=>{
            fetch('/autonomous/status').then(r=>r.json()).then(data=>{
                if (data.grid) this.loadGridFromData(data.grid);
                if (data.path) { this.path = data.path; }
                if (data.path_trace) { this.pathTrace = data.path_trace; }
                if (data.robot_position) { this.robotPosition = data.robot_position; }
                if (Number.isFinite(data.robot_heading_deg)) { this.robotHeading = data.robot_heading_deg; }
                if (typeof data.current_waypoint !== 'undefined') {
                    const st = document.getElementById('planStatus');
                    if (st) {
                        const paused = data.paused && data.pause_reason ? `paused (${data.pause_reason})` : data.status;
                        st.textContent = `Status: ${paused} (${data.current_waypoint}/${data.total_waypoints})`;
                    }
                }
                if (!this.hasAutoRecentered && !this.start) {
                    this.hasAutoRecentered = true;
                    this.recenterStart();
                } else if (this.start) {
                    this.hasAutoRecentered = true;
                }
                this.draw();
            }).catch(()=>{});
        }, 250);
    }

    planPath() {
        fetch('/autonomous/plan',{method:'POST'}).then(r=>r.json()).then(data=>{
            const st = document.getElementById('planStatus');
            if (data.status==='success') {
                this.path = data.path || [];
                if (st) st.textContent = `Status: Path found (${data.stats?.path_length||this.path.length})`;
                this.draw();
            } else {
                if (st) st.textContent = `Status: ${data.status || data.error || 'no path'}`;
            }
        }).catch(err=>console.error('plan error',err));
    }

    executePath() {
        fetch('/autonomous/execute',{method:'POST'}).then(r=>r.json()).then(data=>{
            const st = document.getElementById('planStatus');
            if (data.status) { if (st) st.textContent = `Status: ${data.status}`; }
            else if (data.error) { if (st) st.textContent = `Error: ${data.error}`; }
        }).catch(err=>console.error('exec error',err));
    }

    clearGrid() {
        fetch('/autonomous/grid/clear', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ grid: 'controller' })
        }).then(r=>r.json()).then(data => {
            if (data.grid) this.loadGridFromData(data.grid);
            this.path = [];
            this.pathTrace = [];
        }).catch(()=>{});
    }

    recenterStart() {
        fetch('/autonomous/grid/recenter', {
            method:'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ grid: 'controller' })
        }).then(r=>r.json()).then(data=>{ if (data.grid) this.loadGridFromData(data.grid); }).catch(()=>{});
    }
}

// instantiate when DOM ready
document.addEventListener('DOMContentLoaded', ()=>{
    const g = new AutonomousGridFull('gridCanvasFull');

    // wire minimal controls (already bound by class but ensure buttons exist)
    document.getElementById('planPathBtn')?.addEventListener('click', ()=>g.planPath());
    document.getElementById('executePathBtn')?.addEventListener('click', ()=>g.executePath());
});
