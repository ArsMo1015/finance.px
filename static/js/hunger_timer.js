(function() {
    let remaining = window.deathRemainingAtLoad || 0;
    if (remaining <= 0) return;

    const loadedAt = Date.now() / 1000;

    function update() {
        let elapsed = (Date.now() / 1000) - loadedAt;
        let rem = remaining - elapsed;
        if (rem <= 0) {
            window.location.href = '/die';
            return;
        }
        let overlay = document.getElementById('death-overlay');
        let timer = document.getElementById('hunger-timer');
        if (overlay) overlay.style.opacity = Math.min(1, (30 - rem) / 30);
        if (timer) {
            timer.style.display = 'block';
            timer.innerText = '💀 ' + Math.ceil(rem) + ' сек';
        }
    }

    update();
    setInterval(update, 100);
})();