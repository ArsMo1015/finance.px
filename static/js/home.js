window.onload = function() {
    const canvas = document.getElementById('homeCanvas');
    const ctx = canvas.getContext('2d');
    const actionBtn = document.getElementById('actionBtn');
    const invPanel = document.getElementById('inventory-panel');
    const invList = document.getElementById('inv-list');
    const confirmBar = document.getElementById('confirm-bar');
    const wrenchBtn = document.getElementById('wrench-btn');
    ctx.imageSmoothingEnabled = false;

    let player = { x: 0, y: 0, speed: 2.5, dir: 1, frame: 0 };
    let joy = { active: false, startX: 0, startY: 0, curX: 0, curY: 0, radius: 40 };
    let moveX = 0, moveY = 0;
    let isExiting = false;

    let walls = [];
    let door = {};
    let furnitureObjects = [];
    let boxes = [];
    
    let isEditMode = false;
    let draggedItem = null;
    let hoveredItem = null;
    let dragOffsetX = 0;
    let dragOffsetY = 0;

    const FURNITURE_IMAGES = {
        'Диван': 'divan.png',
        'Телевизор': 'tv.png',
        'Холодильник': 'fridge.png',
        'Корпус ПК': 'pc_case.png',
        'Монитор 60Hz': 'monitor_60.png',
        'Монитор 144Hz': 'monitor_144.png',
        'Офисная клавиатура': 'keyboard_office.png',
        'Механическая клавиатура': 'keyboard_mech.png',
        'Офисная мышь': 'mouse_office.png',
        'Игровая мышь': 'mouse_gaming.png'
    };
    const loadedImages = {};

    for (const [name, file] of Object.entries(FURNITURE_IMAGES)) {
        let img = new Image();
        img.onerror = () => console.warn('Нет картинки: static/furniture/' + file);
        img.src = '/static/furniture/' + file;
        loadedImages[name] = img;
    }

    const FURNITURE_SLOTS = {
        'Диван': { w: 100, h: 50, icon: '🛋️' },
        'Телевизор': { w: 80, h: 40, icon: '📺' },
        'Холодильник': { w: 50, h: 70, icon: '🧊' },
        'Корпус ПК': { w: 35, h: 50, icon: '🗄️' },
        'Монитор 60Hz': { w: 60, h: 40, icon: '🖥️' },
        'Монитор 144Hz': { w: 70, h: 45, icon: '🖥️' },
        'Офисная клавиатура': { w: 40, h: 15, icon: '⌨️' },
        'Механическая клавиатура': { w: 45, h: 18, icon: '⌨️' },
        'Офисная мышь': { w: 15, h: 20, icon: '🖱️' },
        'Игровая мышь': { w: 18, h: 25, icon: '🖱️' }
    };

    function initHome() {
        canvas.width = canvas.parentElement.clientWidth;
        canvas.height = canvas.parentElement.clientHeight;
        
        const cx = canvas.width / 2;
        const cy = canvas.height / 2;
        const wallThick = 20;

        const roomW = Math.min(canvas.width - 40, 450);
        const roomH = Math.min(canvas.height - 40, 350);
        const roomX = (canvas.width - roomW) / 2;
        const roomY = (canvas.height - roomH) / 2;

        walls = [
            {x: roomX, y: roomY, w: roomW, h: wallThick},
            {x: roomX, y: roomY, w: wallThick, h: roomH},
            {x: roomX + roomW - wallThick, y: roomY, w: wallThick, h: roomH},
            {x: roomX, y: roomY + roomH - wallThick, w: roomW, h: wallThick}
        ];

        door = {x: roomX + roomW/2 - 30, y: roomY + roomH - wallThick, w: 60, h: wallThick};
        
        // ПРОВЕРКА СОХРАНЕННОЙ ПОЗИЦИИ (ЧТОБЫ НЕ ТЕЛЕПОРТИРОВАЛО К ДВЕРИ)
        let savedHomePos = localStorage.getItem('homePlayerPos');
        if (savedHomePos) {
            let p = JSON.parse(savedHomePos);
            player.x = p.x;
            player.y = p.y;
            localStorage.removeItem('homePlayerPos');
        } else {
            player.x = door.x + 30; 
            player.y = door.y - 40;
        }

        furnitureObjects = [];
        if (initialFurniture && initialFurniture !== "None" && initialFurniture !== null && initialFurniture !== "") {
            if (initialFurniture.includes(':')) {
                let items = initialFurniture.split('|');
                let spawnOffset = 0;
                items.forEach(itemStr => {
                    let parts = itemStr.split(':');
                    if (parts.length === 2) {
                        let name = parts[0];
                        let coords = parts[1].split(',');
                        if (coords.length >= 2) {
                            let x = parseFloat(coords[0]);
                            let y = parseFloat(coords[1]);
                            let rot = coords.length > 2 ? parseInt(coords[2]) : 0;
                            
                            if (FURNITURE_SLOTS[name]) {
                                let base = FURNITURE_SLOTS[name];
                                let w = base.w, h = base.h;
                                if (rot % 2 !== 0) { w = base.h; h = base.w; }
                                
                                if (x === -1 || y === -1) {
                                    x = roomX + roomW/2 - w/2 + (spawnOffset * 30);
                                    y = roomY + roomH/2 - h/2 + (spawnOffset * 30);
                                    spawnOffset++;
                                }
                                
                                furnitureObjects.push({ name: name, x: x, y: y, rot: rot, w: w, h: h, icon: base.icon });
                            }
                        }
                    }
                });
            } else {
                let owned = initialFurniture.split(',').map(s => s.trim()).filter(s => s !== "");
                owned.forEach((name, i) => {
                    if (FURNITURE_SLOTS[name]) {
                        let base = FURNITURE_SLOTS[name];
                        furnitureObjects.push({ name: name, x: walls[1].x + 20 + (i*40), y: walls[0].y + 20, rot: 0, w: base.w, h: base.h, icon: base.icon });
                    }
                });
            }
        }

        boxes = [];
        let boxX = roomX + roomW/2;
        let boxY = roomY + roomH/2;
        carriedBoxes.forEach((box, index) => {
            boxes.push({
                id: box.id, name: box.item, x: boxX, y: boxY, w: 30, h: 30, isBox: true
            });
            boxX += 35;
            if (boxX > roomX + roomW - 50) {
                boxX = roomX + roomW/2; boxY += 35;
            }
        });
    }

    initHome();
    window.addEventListener('resize', initHome);

    window.toggleInventory = function() {
        if (!isEditMode) {
            isEditMode = true;
            wrenchBtn.style.display = 'none';
            confirmBar.style.display = 'flex';
            document.querySelector('.exit-btn').style.display = 'none';
            actionBtn.style.display = 'none';
            updateInventoryList();
            invPanel.style.display = 'flex';
        } else {
            invPanel.style.display = invPanel.style.display === 'flex' ? 'none' : 'flex';
        }
    };

    window.updateInventoryList = function() {
        invList.innerHTML = '';
        if (carriedBoxes.length === 0) {
            invList.innerHTML = '<div style="font-size:12px; color:#94a3b8; text-align:center;">Нет мебели</div>';
            return;
        }
        carriedBoxes.forEach(box => {
            let div = document.createElement('div');
            div.className = 'inv-item';
            div.innerHTML = `<span class="icon">📦</span><span class="name">${box.item}</span>`;
            div.onclick = () => {
                let base = FURNITURE_SLOTS[box.item];
                if (base) {
                    let newObj = {
                        name: box.item,
                        x: walls[1].x + walls[2].x / 2 - base.w/2,
                        y: walls[0].y + walls[3].y / 2 - base.h/2,
                        rot: 0, w: base.w, h: base.h, icon: base.icon,
                        inventoryId: box.id
                    };
                    furnitureObjects.push(newObj);
                    draggedItem = newObj;
                    dragOffsetX = newObj.w / 2;
                    dragOffsetY = newObj.h / 2;
                    
                    carriedBoxes = carriedBoxes.filter(b => b.id !== box.id);
                    invList.removeChild(div);
                }
            };
            invList.appendChild(div);
        });
    };

    window.confirmEdit = function() {
        let data = furnitureObjects.map(f => `${f.name}:${Math.round(f.x)},${Math.round(f.y)},${f.rot}`);
        let layoutStr = data.join('|');
        let placedIds = furnitureObjects.filter(f => f.inventoryId).map(f => f.inventoryId);
        
        fetch('/save_home_layout', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({layout: layoutStr, placed_ids: placedIds})
        }).then(() => window.location.reload());
    };

    window.cancelEdit = function() {
        window.location.reload();
    };

    window.clearRoom = function() {
        if (confirm('Вся мебель вернется в рюкзак. Продолжить?')) {
            fetch('/clear_room', {
                method: 'POST'
            }).then(() => window.location.reload());
        }
    };

    window.exitHome = function() {
        if (isExiting) return;
        isExiting = true;
        window.location.href = '/';
    };

    function startInteraction(mx, my) {
        if (!isEditMode) return false;

        for (let i = furnitureObjects.length - 1; i >= 0; i--) {
            let f = furnitureObjects[i];
            if (mx > f.x && mx < f.x + f.w && my > f.y && my < f.y + f.h) {
                draggedItem = f;
                furnitureObjects.splice(i, 1);
                furnitureObjects.push(f);
                dragOffsetX = mx - f.x;
                dragOffsetY = my - f.y;
                return true;
            }
        }
        return false;
    }

    canvas.addEventListener('touchstart', e => {
        if(isExiting) return;
        e.preventDefault();
        const rect = canvas.getBoundingClientRect();
        const mx = e.touches[0].clientX - rect.left;
        const my = e.touches[0].clientY - rect.top;
        
        if (!isEditMode) {
            joy.active = true; joy.startX = mx; joy.startY = my; joy.curX = mx; joy.curY = my;
        } else {
            startInteraction(mx, my);
        }
    });

    canvas.addEventListener('touchmove', e => {
        if(!isExiting) e.preventDefault();
        const rect = canvas.getBoundingClientRect();
        const mx = e.touches[0].clientX - rect.left;
        const my = e.touches[0].clientY - rect.top;

        if (draggedItem) {
            let nx = mx - dragOffsetX;
            let ny = my - dragOffsetY;
            nx = Math.max(walls[1].x + 10, Math.min(walls[2].x - draggedItem.w - 10, nx));
            ny = Math.max(walls[0].y + 10, Math.min(walls[3].y - draggedItem.h - 10, ny));
            draggedItem.x = nx; draggedItem.y = ny;
        } else if (joy.active) {
            joy.curX = mx; joy.curY = my;
        }
    });

    canvas.addEventListener('touchend', () => {
        if (draggedItem) {
            draggedItem.x = Math.round(draggedItem.x / 10) * 10;
            draggedItem.y = Math.round(draggedItem.y / 10) * 10;
            draggedItem = null;
        }
        joy.active = false; moveX = 0; moveY = 0;
    });

    canvas.addEventListener('mousedown', e => {
        if(isExiting) return;
        const rect = canvas.getBoundingClientRect();
        const mx = e.clientX - rect.left;
        const my = e.clientY - rect.top;
        
        if (!isEditMode) {
            joy.active = true; joy.startX = mx; joy.startY = my; joy.curX = mx; joy.curY = my;
        } else {
            startInteraction(mx, my);
        }
    });

    canvas.addEventListener('mousemove', e => {
        const rect = canvas.getBoundingClientRect();
        const mx = e.clientX - rect.left;
        const my = e.clientY - rect.top;

        if (draggedItem) {
            let nx = mx - dragOffsetX;
            let ny = my - dragOffsetY;
            nx = Math.max(walls[1].x + 10, Math.min(walls[2].x - draggedItem.w - 10, nx));
            ny = Math.max(walls[0].y + 10, Math.min(walls[3].y - draggedItem.h - 10, ny));
            draggedItem.x = nx; draggedItem.y = ny;
        } else {
            if (joy.active && !isExiting && !isEditMode) {
                joy.curX = mx; joy.curY = my;
            }
            
            if (isEditMode) {
                hoveredItem = null;
                for (let i = furnitureObjects.length - 1; i >= 0; i--) {
                    let f = furnitureObjects[i];
                    if (mx > f.x && mx < f.x + f.w && my > f.y && my < f.y + f.h) {
                        hoveredItem = f; break;
                    }
                }
                canvas.style.cursor = hoveredItem ? 'grab' : 'default';
                if (draggedItem) canvas.style.cursor = 'grabbing';
            }
        }
    });

    canvas.addEventListener('mouseup', () => {
        if (draggedItem) {
            draggedItem.x = Math.round(draggedItem.x / 10) * 10;
            draggedItem.y = Math.round(draggedItem.y / 10) * 10;
            draggedItem = null;
            if (isEditMode) canvas.style.cursor = 'default';
        }
        joy.active = false; moveX = 0; moveY = 0;
    });

    let keys = {};
    window.addEventListener('keydown', e => {
        keys[e.key.toLowerCase()] = true;
        if(['arrowup', 'arrowdown', 'arrowleft', 'arrowright', 'w', 'a', 's', 'd'].includes(e.key.toLowerCase())) e.preventDefault();

        if (e.key.toLowerCase() === 'r' || e.key.toLowerCase() === 'к') {
            if (draggedItem) {
                draggedItem.rot = (draggedItem.rot + 1) % 4;
                let temp = draggedItem.w;
                draggedItem.w = draggedItem.h;
                draggedItem.h = temp;
                
                draggedItem.x = Math.max(walls[1].x + 10, Math.min(walls[2].x - draggedItem.w - 10, draggedItem.x));
                draggedItem.y = Math.max(walls[0].y + 10, Math.min(walls[3].y - draggedItem.h - 10, draggedItem.y));
            }
        }
        
        if (e.key === 'Escape' && isEditMode) {
            window.cancelEdit();
        }
    });
    window.addEventListener('keyup', e => keys[e.key.toLowerCase()] = false);

    function checkCollision(nx, ny) {
        for (let w of walls) {
            if (w.y === door.y && nx > door.x && nx < door.x + door.w) continue;
            if (nx > w.x - 8 && nx < w.x + w.w + 8 && ny > w.y - 8 && ny < w.y + w.h + 8) return true;
        }
        for (let f of furnitureObjects) {
            if (f === draggedItem) continue;
            if (nx > f.x - 10 && nx < f.x + f.w + 10 && ny > f.y - 10 && ny < f.y + f.h + 10) return true;
        }
        for (let b of boxes) {
            if (nx > b.x - 10 && nx < b.x + b.w + 10 && ny > b.y - 10 && ny < b.y + b.h + 10) return true;
        }
        return false;
    }

    function gameLoop() {
        requestAnimationFrame(gameLoop);
        if (isExiting) return;

        if (!isEditMode) {
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
        } else {
            moveX = 0; moveY = 0; 
        }
        
        if (moveX !== 0 || moveY !== 0) {
            let nx = player.x + moveX * player.speed;
            let ny = player.y + moveY * player.speed;
            if (!checkCollision(nx, player.y)) player.x = nx;
            if (!checkCollision(player.x, ny)) player.y = ny;
            player.frame += 0.15; 
            if (moveX > 0) player.dir = 1; else if (moveX < 0) player.dir = -1;
        }

        if (player.y > door.y + 10 && player.x > door.x && player.x < door.x + door.w && !isEditMode) {
            window.exitHome();
            return;
        }

        if (!isEditMode) {
            for (let b of boxes) {
                let dist = Math.hypot(player.x - (b.x + b.w/2), player.y - (b.y + b.h/2));
                if (dist < 50) {
                    actionBtn.style.display = 'block';
                    actionBtn.innerText = 'Распаковать ' + b.name;
                    actionBtn.onclick = () => {
                        // СОХРАНЯЕМ ПОЗИЦИЮ ПЕРЕД РАСПАКОВКОЙ
                        localStorage.setItem('homePlayerPos', JSON.stringify({x: player.x, y: player.y}));
                        
                        fetch('/unpack_furn', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                            body: 'id=' + b.id + '&item=' + encodeURIComponent(b.name)
                        }).then(() => window.location.reload());
                    };
                    break;
                } else {
                    actionBtn.style.display = 'none';
                }
            }
        }

        draw();
    }

    function drawFurniture(f) {
        let isDragged = f === draggedItem;
        let isHovered = f === hoveredItem;
        
        ctx.fillStyle = 'rgba(0,0,0,0.4)';
        ctx.fillRect(f.x + 4, f.y + 4, f.w, f.h);

        ctx.fillStyle = isDragged ? 'rgba(56,189,248,0.2)' : (isHovered ? 'rgba(255,255,255,0.1)' : 'rgba(30,41,59,0.6)');
        ctx.fillRect(f.x, f.y, f.w, f.h);
        
        ctx.strokeStyle = isDragged ? '#38bdf8' : '#334155';
        ctx.lineWidth = isDragged ? 2 : 1;
        ctx.strokeRect(f.x, f.y, f.w, f.h);

        let img = loadedImages[f.name];
        if (img && img.complete && img.naturalWidth > 0) {
            ctx.drawImage(img, f.x, f.y, f.w, f.h);
        } else {
            let fontSize = Math.min(f.w, f.h) * 0.7;
            ctx.font = `${fontSize}px Arial`; 
            ctx.textAlign = 'center'; 
            ctx.textBaseline = 'middle';
            ctx.fillText(f.icon, f.x + f.w/2, f.y + f.h/2);
        }

        ctx.font = 'bold 11px Arial'; 
        ctx.fillStyle = '#cbd5e1';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'top';
        ctx.fillText(f.name, f.x + f.w/2, f.y + f.h + 5);

        if (isHovered || isDragged) {
            ctx.fillStyle = 'rgba(0,0,0,0.8)';
            ctx.fillRect(f.x + f.w - 18, f.y - 5, 22, 18);
            ctx.fillStyle = '#fff'; ctx.font = 'bold 12px Arial'; ctx.textBaseline = 'middle';
            ctx.fillText('R', f.x + f.w - 7, f.y + 5);
        }
    }

    function draw() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        
        ctx.fillStyle = '#0f172a';
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        ctx.fillStyle = '#334155';
        ctx.fillRect(walls[1].x, walls[0].y, walls[1].w + walls[2].w, walls[0].h + walls[3].h);

        ctx.strokeStyle = '#475569'; ctx.lineWidth = 1;
        for(let i=walls[1].x; i<walls[2].x; i+=40) {
            for(let j=walls[0].y; j<walls[3].y; j+=40) {
                ctx.strokeRect(i, j, 40, 40);
            }
        }

        ctx.fillStyle = '#1e293b';
        walls.forEach(w => ctx.fillRect(w.x, w.y, w.w, w.h));
        
        ctx.fillStyle = '#38bdf8';
        ctx.fillRect(door.x, door.y, door.w, door.h);

        furnitureObjects.forEach(f => drawFurniture(f));

        boxes.forEach(b => {
            ctx.fillStyle = 'rgba(0,0,0,0.4)';
            ctx.fillRect(b.x + 3, b.y + 3, b.w, b.h);
            
            ctx.fillStyle = '#b45309';
            ctx.fillRect(b.x, b.y, b.w, b.h);
            ctx.fillStyle = '#78350f';
            ctx.fillRect(b.x + b.w/2 - 3, b.y, 6, b.h);
            
            ctx.fillStyle = '#f8fafc';
            ctx.font = '16px Arial'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
            ctx.fillText('📦', b.x + b.w/2, b.y + b.h/2);
        });

        ctx.save(); ctx.translate(player.x, player.y); ctx.scale(player.dir, 1);
        let legOffset = Math.sin(player.frame) * 3;
        ctx.fillStyle = '#1e293b'; ctx.fillRect(-6, 14 + legOffset, 4, 6); ctx.fillRect(2, 14 - legOffset, 4, 6);
        ctx.fillStyle = '#3b82f6'; ctx.fillRect(-8, -2, 16, 16);
        ctx.fillStyle = '#2563eb'; ctx.fillRect(-10, 0, 2, 10); ctx.fillRect(8, 0, 2, 10);
        ctx.fillStyle = '#fcd34d'; ctx.fillRect(-6, -14, 12, 12);
        ctx.fillStyle = '#78350f'; ctx.fillRect(-6, -16, 12, 4); ctx.fillRect(-8, -14, 2, 6);
        ctx.fillStyle = '#000'; ctx.fillRect(2, -10, 2, 2); ctx.fillRect(-2, -10, 1, 2); 
        ctx.restore();

        if (joy.active && !isEditMode) {
            ctx.beginPath(); ctx.arc(joy.startX, joy.startY, joy.radius, 0, Math.PI*2); ctx.fillStyle = 'rgba(15,23,42,0.5)'; ctx.fill();
            let dx = joy.curX - joy.startX; let dy = joy.curY - joy.startY;
            let dist = Math.hypot(dx, dy); if (dist > joy.radius) { dx = (dx/dist)*joy.radius; dy = (dy/dist)*joy.radius; }
            ctx.beginPath(); ctx.arc(joy.startX + dx, joy.startY + dy, 20, 0, Math.PI*2); ctx.fillStyle = 'rgba(56,189,248,0.8)'; ctx.fill();
        }
    }

    requestAnimationFrame(gameLoop);
};