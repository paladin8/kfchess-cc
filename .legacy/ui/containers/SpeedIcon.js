import React, { Component } from 'react';
import { Tooltip } from 'react-tippy';

import * as Speed from '../util/Speed.js';

export default class SpeedIcon extends Component {

    render() {
        const { speed, iconOnly, rated } = this.props;
        const displayName = Speed.getDisplayName(speed);

        return (
            <div className='speed-icon'>
                {!iconOnly ? displayName + ' Speed' + (rated ? ' (Rated)' : '') : ''}
                {speed === 'standard' &&
                    <Tooltip
                        title={displayName}
                    >
                        <i className='fas fa-clock speed-icon-i' />
                    </Tooltip>
                }
                {speed === 'lightning' &&
                    <Tooltip
                        title={displayName}
                    >
                        <i className='fas fa-bolt speed-icon-i' />
                    </Tooltip>
                }
            </div>
        );
    }
};
