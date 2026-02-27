import openSocket from 'socket.io-client';

const PING_INTERVAL = 1000 * 60 * 5;  // 5 min

export default class Listener {

    constructor(userId, inviteCallback, onlineCallback) {
        this.userId = userId;
        this.inviteCallback = inviteCallback;
        this.onlineCallback = onlineCallback;

        this.destroyed = false;

        this.connect();
    }

    connect() {
        this.socket = openSocket();
        this.socket.on('disconnect', () => {
            if (!this.destroyed) {
                this.socket.close();
                this.connect();
            }
        });

        this.socket.on('invite', this.inviteCallback);
        this.socket.on('online', this.onlineCallback);

        this.socket.emit('listen', JSON.stringify({ userId: this.userId }));

        if (this.interval) {
            clearInterval(this.interval);
        }

        this.interval = setInterval(() => this.ping(), PING_INTERVAL);
    }

    ping() {
        this.socket.emit('uping', JSON.stringify({ userId: this.userId }));
    }

    destroy() {
        clearInterval(this.interval);

        this.destroyed = true;
        this.socket.close();
    }
};
