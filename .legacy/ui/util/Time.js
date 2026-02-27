export function renderGameTime(ticks) {
    const minutes = Math.floor(ticks / 600);
    const seconds = Math.floor((ticks % 600) / 10);
    return minutes.toString() + ':' + ('00' + seconds.toString()).substr(-2, 2);
};
