import * as amplitude from '@amplitude/analytics-browser';
import { sessionReplayPlugin } from '@amplitude/plugin-session-replay-browser';
import React from 'react';
import ReactDOM from 'react-dom';
import ReactModal from 'react-modal';

import App from './containers/App';

import 'react-tippy/dist/tippy.css';
import './styles/index.less';

amplitude.init(AMPLITUDE_API_KEY, {
	minIdLength: 1,
	autocapture: {
		elementInteractions: true,
	}
});

const sessionReplayTracking = sessionReplayPlugin();
amplitude.add(sessionReplayTracking);

ReactDOM.render(<App />, document.getElementById('app'));

ReactModal.setAppElement('#app');
ReactModal.defaultStyles.overlay.backgroundColor = 0x000000;
