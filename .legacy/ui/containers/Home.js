import * as amplitude from '@amplitude/analytics-browser';
import React, { Component } from 'react';
import { Link } from 'react-router-dom';

export default class Home extends Component {

    constructor(props) {
        super(props);

        this.state = {
            friendlySpeed: (window.localStorage && window.localStorage.friendlySpeed) || 'standard',
        };
    }

    componentDidMount() {
        amplitude.track('Visit Home Page');
    }

    changeFriendlySpeed(friendlySpeed) {
        amplitude.track('Change Friendly Speed', { friendlySpeed });
        this.setState({ friendlySpeed });

        if (window.localStorage) {
            window.localStorage.friendlySpeed = friendlySpeed;
        }
    }

    render () {
        const { friendlySpeed } = this.state;
        const { expReady, experiment } = this.props;

        let main = 'Chess Without Turns';
        let sub = "The world's most popular strategy game goes real-time.";

        const homeTextFlagKey = 'home-text-2023-04';
        const variant = experiment.variant(homeTextFlagKey);
        if (variant && variant.payload) {
            main = variant.payload.main;
            sub = variant.payload.sub;
        }

        return (
            <div className='home'>
                <div className='home-banner'>
                    <div className='home-banner-inner'>
                        <div className='home-banner-video'>
                            <video autoPlay loop muted playsInline>
                                <source src='/static/banner-video.mp4' type='video/mp4' />
                            </video>
                        </div>
                        <div className='home-banner-text'>
                            <div className='home-banner-text-main'>
                                {main}
                            </div>
                            <div className='home-banner-text-sub'>
                                {sub}
                            </div>
                        </div>
                    </div>
                </div>
                <div className='home-play-buttons'>
                    <div className='home-play-button-wrapper'>
                        <Link to='/campaign'>
                            <div className='home-play-button'>
                                Campaign
                            </div>
                        </Link>
                        <div className='home-play-subtitle'>
                            Complete Solo Missions
                        </div>
                    </div>
                    <div className='home-play-button-wrapper'>
                        <div
                            className='home-play-button'
                            onClick={() => this.props.createNewGame(friendlySpeed, true, 'novice')}
                        >
                            Play vs AI
                        </div>
                        <div className='home-play-option-wrapper'>
                            <div
                                className={`home-play-option ${friendlySpeed === 'standard' ? 'selected' : ''}`}
                                onClick={() => this.changeFriendlySpeed('standard')}
                            >
                                Standard
                            </div>
                            <div
                                className={`home-play-option ${friendlySpeed === 'lightning' ? 'selected' : ''}`}
                                onClick={() => this.changeFriendlySpeed('lightning')}
                            >
                                Lightning
                            </div>
                        </div>
                    </div>
                    <div className='home-play-button-wrapper'>
                        <div
                            className='home-play-button'
                            onClick={() => this.props.createNewGame(friendlySpeed, false)}
                        >
                            Play vs Friend
                        </div>
                        <div className='home-play-option-wrapper'>
                            <div
                                className={`home-play-option ${friendlySpeed === 'standard' ? 'selected' : ''}`}
                                onClick={() => this.changeFriendlySpeed('standard')}
                            >
                                Standard
                            </div>
                            <div
                                className={`home-play-option ${friendlySpeed === 'lightning' ? 'selected' : ''}`}
                                onClick={() => this.changeFriendlySpeed('lightning')}
                            >
                                Lightning
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        );
    }
};
