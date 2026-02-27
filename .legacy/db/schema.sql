CREATE TABLE users (
    id            BIGSERIAL PRIMARY KEY,
    email         TEXT UNIQUE,
    username      TEXT UNIQUE,
    picture_url   TEXT,
    ratings       JSONB,
    join_time     TIMESTAMP WITHOUT TIME ZONE,
    last_online   TIMESTAMP WITHOUT TIME ZONE,
    current_game  JSONB
);

CREATE INDEX users_last_online_idx ON users (last_online);


CREATE TABLE user_game_history (
    id           BIGSERIAL PRIMARY KEY,
    user_id      BIGINT,
    game_time    TIMESTAMP WITHOUT TIME ZONE,
    game_info    JSONB
);

CREATE INDEX user_game_history_user_id_game_time_idx ON user_game_history (user_id, game_time);


CREATE TABLE game_history (
    id      BIGSERIAL PRIMARY KEY,
    replay  JSONB
);


CREATE TABLE active_games (
    id         BIGSERIAL PRIMARY KEY,
    server     INT,
    game_id    TEXT,
    game_info  JSONB
);

CREATE INDEX active_games_server_game_id_idx ON active_games (server, game_id);


CREATE TABLE campaign_progress (
    id        BIGSERIAL PRIMARY KEY,
    user_id   BIGINT UNIQUE,
    progress  JSONB
);
