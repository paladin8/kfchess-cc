import React, { Component } from 'react';

export default class ProfilePic extends Component {

    render() {
        const { user, className } = this.props;

        return (
            <div className={`profile-pic ${className || ''}`}>
                <img src={user.pictureUrl || '/static/default-profile.jpg'} />
            </div>
        );
    }
};
