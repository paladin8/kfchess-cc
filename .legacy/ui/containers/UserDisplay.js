import React, { Component } from 'react';
import { Link } from 'react-router-dom';

import ProfilePic from './ProfilePic.js';

export default class UserDisplay extends Component {

    render() {
        const { value, knownUsers } = this.props;

        let user = null;
        let text = 'Anonymous';
        if (value.startsWith('b')) {
            if (value.length > 2) {
                const difficulty = value.substring(2);
                text = 'AI Player (' + difficulty.charAt(0).toUpperCase() + difficulty.substring(1) + ')';
            } else {
                text = 'AI Player';
            }
        } else if (value.startsWith('c:')) {
            const level = parseInt(value.substring(2)) + 1;
            text = 'Campaign Level ' + level;
        } else if (value.startsWith('u:')) {
            const userId = value.substring(2);
            user = knownUsers[userId];
        }

        return (
            <div className='user-display'>
                {user &&
                    <Link to={`/profile/${user.userId}`} className='user-display-user-wrapper'>
                        <ProfilePic className='user-display-profile-pic' user={user} />
                        <div className='user-display-username'>
                            {user.username}
                        </div>
                    </Link>
                }
                {!user && <div className='user-display-text'>{text}</div>}
            </div>
        );
    }
};
