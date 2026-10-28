window.onload = function() {
    const canvas = document.getElementById('shopCanvas');
    const ctx = canvas.getContext('2d');
    const actionBtn = document.getElementById('actionBtn');
    ctx.imageSmoothingEnabled = false;

    let shopPlayer = { x: 0, y: 0, speed: 2.5, dir: 1, frame: 0 };
    let joy = { active: false, startX: 0, startY: 0, curX: 0, curY: 0, radius: 40 };
    let moveX = 0, moveY = 0;
    let nearbyTarget = null;
    let isExiting = false;

    let shelves = [];
    let cashier = {};
    let door = {};
    let walls = [];

    function initShop() {
        if (!canvas.parentElement) return;
        canvas.width = canvas.parentElement.clientWidth;
        canvas.height = canvas.parentElement.clientHeight;
        
        const cx = canvas.width / 2;
        const cy = canvas.height / 2;
        const wallThick = 20;

        walls = [
            {x: 0, y: 0, w: canvas.width, h: wallThick},
            {x: 0, y: 0, w: wallThick, h: canvas.height},
            {x: canvas.width - wallThick, y: 0, w: wallThick, h: canvas.height},
            {x: 0, y: canvas.height - wallThick, w: canvas.width, h: wallThick}
        ];

        door = {x: cx - 30, y: canvas.height - wallThick, w: 60, h: wallThick};
        shopPlayer.x = cx; 
        shopPlayer.y = canvas.height - 60;

        shelves = [
            { id: 'Хлеб', name: 'Хлеб', icon: '🍞', price: 50, x: cx - 120, y: cy - 80, w: 80, h: 40, color: '#a16207' },
            { id: 'Пицца', name: 'Пицца', icon: '🍕', price: 300, x: cx - 120, y: cy, w: 80, h: 40, color: '#a16207' },
            { id: 'Элитный стейк', name: 'Стейк', icon: '🥩', price: 2000, x: cx - 120, y: cy + 80, w: 80, h: 40, color: '#a16207' }
        ];

        cashier = { id: 'Касса', name: 'Касса', icon: '💳', x: cx + 60, y: cy - 20, w: 80, h: 60, color: '#1e293b' };
    }

    initShop();
    window.addEventListener('resize', initShop);

    // === Управление джойстиком ===
    canvas.addEventListener('touchstart', e => {
        if(isExiting) return;
        e.preventDefault();
        const rect = canvas.getBoundingClientRect();
        const tx = e.touches[0].clientX - rect.left; 
        const ty = e.touches[0].clientY - rect.top;
        joy.active = true; joy.startX = tx; joy.startY = ty; joy.curX = tx; joy.curY = ty;
    });
    canvas.addEventListener('touchmove', e => {
        if(!joy.active || isExiting) return; e.preventDefault();
        const rect = canvas.getBoundingClientRect();
        joy.curX = e.touches[0].clientX - rect.left; 
        joy.curY = e.touches[0].clientY - rect.top;
    });
    canvas.addEventListener('touchend', e => { e.preventDefault(); joy.active = false; moveX = 0; moveY = 0; });
    canvas.addEventListener('mousedown', e => {
        if(isExiting) return;
        const rect = canvas.getBoundingClientRect();
        joy.active = true; joy.startX = e.clientX - rect.left; joy.startY = e.clientY - rect.top; joy.curX = joy.startX; joy.curY = joy.startY;
    });
    canvas.addEventListener('mousemove', e => { 
        if(joy.active && !isExiting) { const rect = canvas.getBoundingClientRect(); joy.curX = e.clientX - rect.left; joy.curY = e.clientY - rect.top; } 
    });
    canvas.addEventListener('mouseup', () => { joy.active = false; moveX = 0; moveY = 0; });

    // === КЛАВИАТУРА ДЛЯ МАГАЗИНА ===
    let keys = {};
    window.addEventListener('keydown', e => {
        keys[e.key.toLowerCase()] = true;
        if(['arrowup', 'arrowdown', 'arrowleft', 'arrowright', 'w', 'a', 's', 'd'].includes(e.key.toLowerCase())) e.preventDefault();
    });
    window.addEventListener('keyup', e => keys[e.key.toLowerCase()] = false);

    // === Коллизии ===
    function checkShopCollision(nx, ny) {
        for (let w of walls) {
            if (w.y === canvas.height - 20 && nx > door.x && nx < door.x + door.w) continue;
            if (nx > w.x - 8 && nx < w.x + w.w + 8 && ny > w.y - 8 && ny < w.y + w.h + 8) return true;
        }
        for (let s of shelves) {
            if (nx > s.x - 10 && nx < s.x + s.w + 10 && ny > s.y - 10 && ny < s.y + s.h + 10) return true;
        }
        if (nx > cashier.x - 10 && nx < cashier.x + cashier.w + 10 && ny > cashier.y - 10 && ny < cashier.y + cashier.h + 10) return true;
        if (ny > canvas.height - 20 && !(nx > door.x && nx < door.x + door.w)) return true;
        return false;
    }

    // === UI Корзины ===
    function updateCartUI(cart, total) {
        const itemsDiv = document.getElementById('cartItems');
        const totalDiv = document.getElementById('cartTotal');
        if (Object.keys(cart).length === 0) {
            itemsDiv.innerText = 'Пусто';
        } else {
            let html = '';
            for (const [item, qty] of Object.entries(cart)) {
                html += `<div style="display:flex; justify-content:space-between;"><span>${item}</span> <b>x${qty}</b></div>`;
            }
            itemsDiv.innerHTML = html;
        }
        totalDiv.innerText = `Итого: ${total} ₽`;
    }

    // === Выход из магазина ===
    window.exitShop = function() {
        if (isExiting) return;
        isExiting = true;
        actionBtn.style.display = 'none';
        
        fetch('/shop/clear', {method:'POST'}).then(() => {
            window.location.href = '/';
        });
    };

    // === Игровой цикл ===
    function gameLoop() {
        requestAnimationFrame(gameLoop);
        if (isExiting) return;

        if (joy.active) {
            let dx = joy.curX - joy.startX; let dy = joy.curY - joy.startY;
            let dist = Math.hypot(dx, dy);
            if (dist > 0) {
                let maxDist = 30; if (dist > maxDist) { dx = (dx/dist)*maxDist; dy = (dy/dist)*maxDist; }
                moveX = dx / maxDist; moveY = dy / maxDist;
            }
        } else {
            moveX = 0; moveY = 0;
            if (keys['w'] || keys['arrowup'] || keys['ц']) moveY = -1;
            if (keys['s'] || keys['arrowdown'] || keys['ы']) moveY = 1;
            if (keys['a'] || keys['arrowleft'] || keys['ф']) moveX = -1;
            if (keys['d'] || keys['arrowright'] || keys['в']) moveX = 1;
            if (moveX !== 0 && moveY !== 0) { moveX *= 0.707; moveY *= 0.707; }
        }
        
        if (moveX !== 0 || moveY !== 0) {
            let nx = shopPlayer.x + moveX * shopPlayer.speed;
            let ny = shopPlayer.y + moveY * shopPlayer.speed;
            if (!checkShopCollision(nx, shopPlayer.y)) shopPlayer.x = nx;
            if (!checkShopCollision(shopPlayer.x, ny)) shopPlayer.y = ny;
            shopPlayer.frame += 0.15; 
            if (moveX > 0) shopPlayer.dir = 1; else if (moveX < 0) shopPlayer.dir = -1;
        }

        if (shopPlayer.y > canvas.height - 10 && shopPlayer.x > door.x && shopPlayer.x < door.x + door.w) {
            window.exitShop();
            return;
        }

        nearbyTarget = null;
        let minDist = 9999;

        for (let s of shelves) {
            let dist = Math.hypot(shopPlayer.x - (s.x + s.w/2), shopPlayer.y - (s.y + s.h/2));
            if (dist < 60 && dist < minDist) {
                minDist = dist;
                nearbyTarget = s;
            }
        }
        
        let distCashier = Math.hypot(shopPlayer.x - (cashier.x + cashier.w/2), shopPlayer.y - (cashier.y + cashier.h/2));
        if (distCashier < 70 && distCashier < minDist) {
            minDist = distCashier;
            nearbyTarget = cashier;
        }

        if (nearbyTarget) {
            actionBtn.style.display = 'block';
            if (nearbyTarget.id === 'Касса') {
                actionBtn.innerText = 'Оплатить 💳';
                actionBtn.onclick = () => {
                    fetch('/shop/pay', {method:'POST'}).then(r => r.json()).then(data => {
                        if (data.status === 'ok') {
                            alert(data.msg);
                            updateCartUI({}, 0);
                            window.location.reload();
                        } else {
                            alert(data.msg);
                        }
                    });
                };
            } else {
                actionBtn.innerText = 'Взять ' + nearbyTarget.name;
                actionBtn.onclick = () => {
                    fetch('/shop/add', {
                        method:'POST',
                        headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                        body: 'item=' + encodeURIComponent(nearbyTarget.id)
                    }).then(r => r.json()).then(data => {
                        if(data.status === 'ok') updateCartUI(data.cart, data.total);
                    });
                };
            }
        } else {
            actionBtn.style.display = 'none';
        }

        draw();
    }

    function draw() {
        ctx.fillStyle = '#334155';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        
        ctx.strokeStyle = '#475569'; ctx.lineWidth = 1;
        for(let i=0; i<canvas.width; i+=40) {
            for(let j=0; j<canvas.height; j+=40) {
                ctx.strokeRect(i, j, 40, 40);
            }
        }

        ctx.fillStyle = '#1e293b';
        walls.forEach(w => ctx.fillRect(w.x, w.y, w.w, w.h));
        
        ctx.fillStyle = '#38bdf8';
        ctx.fillRect(door.x, door.y, door.w, door.h);

        ctx.fillStyle = '#0f172a';
        ctx.fillRect(cashier.x, cashier.y, cashier.w, cashier.h);
        ctx.fillStyle = '#22c55e';
        ctx.fillRect(cashier.x + 10, cashier.y + 10, 20, 20);
        ctx.font = '24px Arial'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        ctx.fillText('🧑‍💼', cashier.x + cashier.w/2, cashier.y + cashier.h/2 + 10);

        shelves.forEach(s => {
            ctx.fillStyle = '#78350f';
            ctx.fillRect(s.x, s.y, s.w, s.h);
            ctx.fillStyle = '#451a03';
            ctx.fillRect(s.x, s.y + s.h - 10, s.w, 10);
            
            ctx.font = '28px Arial'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
            ctx.fillText(s.icon, s.x + s.w/2, s.y + s.h/2 - 5);

            ctx.fillStyle = 'rgba(15,23,42,0.9)';
            ctx.fillRect(s.x + s.w/2 - 25, s.y + s.h + 5, 50, 18);
            ctx.fillStyle = '#fcd34d';
            ctx.font = 'bold 12px Arial';
            ctx.fillText(s.price + ' ₽', s.x + s.w/2, s.y + s.h + 14);
        });

        ctx.save(); ctx.translate(shopPlayer.x, shopPlayer.y); ctx.scale(shopPlayer.dir, 1);
        let legOffset = Math.sin(shopPlayer.frame) * 3;
        ctx.fillStyle = '#1e293b'; ctx.fillRect(-6, 14 + legOffset, 4, 6); ctx.fillRect(2, 14 - legOffset, 4, 6);
        ctx.fillStyle = '#3b82f6'; ctx.fillRect(-8, -2, 16, 16);
        ctx.fillStyle = '#2563eb'; ctx.fillRect(-10, 0, 2, 10); ctx.fillRect(8, 0, 2, 10);
        ctx.fillStyle = '#fcd34d'; ctx.fillRect(-6, -14, 12, 12);
        ctx.fillStyle = '#78350f'; ctx.fillRect(-6, -16, 12, 4); ctx.fillRect(-8, -14, 2, 6);
        ctx.fillStyle = '#000'; ctx.fillRect(2, -10, 2, 2); ctx.fillRect(-2, -10, 1, 2); 
        ctx.restore();

        if (joy.active) {
            ctx.beginPath(); ctx.arc(joy.startX, joy.startY, joy.radius, 0, Math.PI*2); ctx.fillStyle = 'rgba(15,23,42,0.5)'; ctx.fill();
            let dx = joy.curX - joy.startX; let dy = joy.curY - joy.startY;
            let dist = Math.hypot(dx, dy); if (dist > joy.radius) { dx = (dx/dist)*joy.radius; dy = (dy/dist)*joy.radius; }
            ctx.beginPath(); ctx.arc(joy.startX + dx, joy.startY + dy, 20, 0, Math.PI*2); ctx.fillStyle = 'rgba(56,189,248,0.8)'; ctx.fill();
        }
    }

    requestAnimationFrame(gameLoop);
};