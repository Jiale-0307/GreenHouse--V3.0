
CREATE TABLE IF NOT EXISTS schema_version (
	version INTEGER NOT NULL AUTO_INCREMENT, 
	PRIMARY KEY (version)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin

;

CREATE TABLE IF NOT EXISTS sites (
	id VARCHAR(64) NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	is_debug BOOL NOT NULL, 
	control_verified BOOL NOT NULL, 
	last_seen_at DATETIME(6), 
	PRIMARY KEY (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin

;

CREATE TABLE IF NOT EXISTS users (
	id VARCHAR(36) NOT NULL, 
	username VARCHAR(64) NOT NULL, 
	display_name VARCHAR(100) NOT NULL, 
	password_hash VARCHAR(256) NOT NULL, 
	`role` VARCHAR(16) NOT NULL, 
	enabled BOOL NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (username)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin

;

CREATE TABLE IF NOT EXISTS actuators (
	site_id VARCHAR(64) NOT NULL, 
	id VARCHAR(64) NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	kind VARCHAR(64) NOT NULL, 
	state JSON, 
	mode VARCHAR(16), 
	version VARCHAR(64) NOT NULL, 
	actions JSON NOT NULL, 
	mode_writable BOOL NOT NULL, 
	remote_allowed BOOL NOT NULL, 
	interlock_ok BOOL NOT NULL, 
	feedback_at DATETIME(6), 
	PRIMARY KEY (site_id, id), 
	FOREIGN KEY(site_id) REFERENCES sites (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin

;

CREATE TABLE IF NOT EXISTS alarms (
	id VARCHAR(64) NOT NULL, 
	site_id VARCHAR(64) NOT NULL, 
	level VARCHAR(16) NOT NULL, 
	title VARCHAR(200) NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	occurred_at DATETIME(6) NOT NULL, 
	detail TEXT, 
	can_acknowledge BOOL NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(site_id) REFERENCES sites (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin

;
CREATE INDEX ix_alarms_occurred_at ON alarms (occurred_at);
CREATE INDEX ix_alarms_site_id ON alarms (site_id);

CREATE TABLE IF NOT EXISTS auth_sessions (
	token_hash VARCHAR(64) NOT NULL, 
	user_id VARCHAR(36) NOT NULL, 
	csrf_token VARCHAR(64) NOT NULL, 
	expires_at DATETIME(6) NOT NULL, 
	PRIMARY KEY (token_hash), 
	FOREIGN KEY(user_id) REFERENCES users (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin

;
CREATE INDEX ix_auth_sessions_expires_at ON auth_sessions (expires_at);
CREATE INDEX ix_auth_sessions_user_id ON auth_sessions (user_id);

CREATE TABLE IF NOT EXISTS cameras (
	site_id VARCHAR(64) NOT NULL, 
	id VARCHAR(64) NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	playback_url TEXT, 
	protocol VARCHAR(16), 
	online BOOL, 
	PRIMARY KEY (site_id, id), 
	FOREIGN KEY(site_id) REFERENCES sites (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin

;

CREATE TABLE IF NOT EXISTS chat_sessions (
	id VARCHAR(36) NOT NULL, 
	site_id VARCHAR(64) NOT NULL, 
	user_id VARCHAR(36) NOT NULL, 
	title VARCHAR(100) NOT NULL, 
	created_at DATETIME(6) NOT NULL, 
	busy BOOL NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(site_id) REFERENCES sites (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin

;
CREATE INDEX ix_chat_sessions_site_id ON chat_sessions (site_id);

CREATE TABLE IF NOT EXISTS ingest_receipts (
	site_id VARCHAR(64) NOT NULL, 
	message_id VARCHAR(128) NOT NULL, 
	payload_hash VARCHAR(64) NOT NULL, 
	received_at DATETIME(6) NOT NULL, 
	PRIMARY KEY (site_id, message_id), 
	FOREIGN KEY(site_id) REFERENCES sites (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin

;

CREATE TABLE IF NOT EXISTS metric_definitions (
	site_id VARCHAR(64) NOT NULL, 
	id VARCHAR(64) NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	group_name VARCHAR(64) NOT NULL, 
	source VARCHAR(100) NOT NULL, 
	unit VARCHAR(32), 
	display_order INTEGER NOT NULL, 
	enabled BOOL NOT NULL, 
	value DOUBLE, 
	quality VARCHAR(16) NOT NULL, 
	observed_at DATETIME(6), 
	received_at DATETIME(6), 
	PRIMARY KEY (site_id, id), 
	FOREIGN KEY(site_id) REFERENCES sites (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin

;

CREATE TABLE IF NOT EXISTS metric_evidence (
	site_id VARCHAR(64) NOT NULL, 
	metric_id VARCHAR(64) NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	sources JSON NOT NULL, 
	attempted_at DATETIME(6) NOT NULL, 
	PRIMARY KEY (site_id, metric_id), 
	FOREIGN KEY(site_id) REFERENCES sites (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin

;

CREATE TABLE IF NOT EXISTS metric_samples (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	site_id VARCHAR(64) NOT NULL, 
	metric_id VARCHAR(64) NOT NULL, 
	value DOUBLE, 
	quality VARCHAR(16) NOT NULL, 
	observed_at DATETIME(6), 
	received_at DATETIME(6) NOT NULL, 
	timestamp DATETIME(6) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(site_id) REFERENCES sites (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin

;
CREATE INDEX ix_samples_site_metric_time ON metric_samples (site_id, metric_id, timestamp);

CREATE TABLE IF NOT EXISTS operation_logs (
	id VARCHAR(36) NOT NULL, 
	site_id VARCHAR(64) NOT NULL, 
	actor VARCHAR(64), 
	action VARCHAR(100) NOT NULL, 
	target VARCHAR(100) NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	requested_at DATETIME(6) NOT NULL, 
	result TEXT, 
	PRIMARY KEY (id), 
	FOREIGN KEY(site_id) REFERENCES sites (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin

;
CREATE INDEX ix_operation_logs_requested_at ON operation_logs (requested_at);
CREATE INDEX ix_operation_logs_site_id ON operation_logs (site_id);

CREATE TABLE IF NOT EXISTS parameters (
	site_id VARCHAR(64) NOT NULL, 
	id VARCHAR(64) NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	value DOUBLE, 
	unit VARCHAR(32), 
	minimum DOUBLE, 
	maximum DOUBLE, 
	step DOUBLE, 
	writable BOOL NOT NULL, 
	version VARCHAR(64) NOT NULL, 
	feedback_at DATETIME(6), 
	PRIMARY KEY (site_id, id), 
	FOREIGN KEY(site_id) REFERENCES sites (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin

;

CREATE TABLE IF NOT EXISTS plc_states (
	site_id VARCHAR(64) NOT NULL, 
	id VARCHAR(64) NOT NULL, 
	payload JSON NOT NULL, 
	received_at DATETIME(6) NOT NULL, 
	PRIMARY KEY (site_id, id), 
	FOREIGN KEY(site_id) REFERENCES sites (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin

;

CREATE TABLE IF NOT EXISTS realtime_events (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	site_id VARCHAR(64) NOT NULL, 
	user_id VARCHAR(36), 
	type VARCHAR(32) NOT NULL, 
	payload JSON NOT NULL, 
	emitted_at DATETIME(6) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(site_id) REFERENCES sites (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin

;
CREATE INDEX ix_realtime_events_site_id ON realtime_events (site_id);

CREATE TABLE IF NOT EXISTS alarm_lifecycles (
	alarm_id VARCHAR(64) NOT NULL, 
	source VARCHAR(64) NOT NULL, 
	acknowledged_at DATETIME(6), 
	recovered_at DATETIME(6), 
	PRIMARY KEY (alarm_id), 
	FOREIGN KEY(alarm_id) REFERENCES alarms (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin

;

CREATE TABLE IF NOT EXISTS chat_messages (
	id VARCHAR(36) NOT NULL, 
	session_id VARCHAR(36) NOT NULL, 
	`role` VARCHAR(16) NOT NULL, 
	content TEXT NOT NULL, 
	created_at DATETIME(6) NOT NULL, 
	control_intent JSON, 
	PRIMARY KEY (id), 
	FOREIGN KEY(session_id) REFERENCES chat_sessions (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin

;
CREATE INDEX ix_chat_messages_session_id ON chat_messages (session_id);

CREATE TABLE IF NOT EXISTS commands (
	id VARCHAR(36) NOT NULL, 
	site_id VARCHAR(64) NOT NULL, 
	user_id VARCHAR(36) NOT NULL, 
	idempotency_key VARCHAR(36) NOT NULL, 
	payload_hash VARCHAR(64) NOT NULL, 
	payload JSON NOT NULL, 
	kind VARCHAR(16) NOT NULL, 
	target_id VARCHAR(64) NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	accepted_at DATETIME(6) NOT NULL, 
	updated_at DATETIME(6) NOT NULL, 
	readback_at DATETIME(6), 
	result TEXT, 
	log_id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_command_key UNIQUE (site_id, user_id, idempotency_key), 
	FOREIGN KEY(site_id) REFERENCES sites (id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(log_id) REFERENCES operation_logs (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin

;
CREATE INDEX ix_commands_site_id ON commands (site_id);
CREATE INDEX ix_commands_status ON commands (status);

CREATE TABLE IF NOT EXISTS session_devices (
	id VARCHAR(36) NOT NULL, 
	token_hash VARCHAR(64) NOT NULL, 
	created_at DATETIME(6) NOT NULL, 
	user_agent VARCHAR(256) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (token_hash), 
	FOREIGN KEY(token_hash) REFERENCES auth_sessions (token_hash) ON DELETE CASCADE
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin

;
