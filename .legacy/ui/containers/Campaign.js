import * as amplitude from '@amplitude/analytics-browser';
import React, { Component } from 'react';
import Modal from 'react-modal';
import { withRouter } from 'react-router';
import { Tooltip } from 'react-tippy';
import { CSSTransition } from 'react-transition-group'

import Spinner from './Spinner.js';
import CampaignLevels, { BELTS, MAX_BELT } from '../util/CampaignLevels.js';

const inIFrame = () => {
    try {
        return window.self !== window.top;
    } catch (e) {
        return true;
    }
};

class Campaign extends Component {

    constructor(props) {
        super(props);

        this.state = {
            belt: null,
            progress: null,
        };
    }

    componentWillMount() {
        this.fetchCampaignInfo(this.props);
    }

    componentWillReceiveProps(nextProps) {
        if (this.props.user != nextProps.user) {
            this.fetchCampaignInfo(nextProps);
        }
    }

    fetchCampaignInfo(props) {
        const { user } = props;

        if (user) {
            amplitude.track('Visit Campaign Page');

            this.props.fetchCampaignInfo(user.userId, data => {
                this.setState({
                    belt: Math.min(MAX_BELT, this.getCurrentBelt(data.progress)),
                    progress: data.progress,
                });
            });
        } else {
            this.setState({
                belt: null,
                progress: null,
            });
        }
    }

    getCurrentBelt(progress) {
        return Object.keys(progress.beltsCompleted).length + 1;
    }

    chooseBelt(belt) {
        const { progress } = this.state;

        amplitude.track('Click Campaign Belt', {
            belt,
            isCompleted: progress.beltsCompleted[belt] === true,
        });

        this.setState({ belt });
    }

    startLevel(level) {
        const { progress } = this.state;

        amplitude.track('Click Campaign Level', {
            level,
            isCompleted: progress.levelsCompleted[level] === true,
        });

        this.props.startCampaignLevel(level);
    }

    render() {
        const { user } = this.props;
        const { belt, progress } = this.state;

        return (
            <div className='campaign'>
                {!user ?
                    this.renderCampaignNoUser()
                    :
                    (!progress ?
                        <Spinner />
                        :
                        <div className='campaign-wrapper'>
                            <div className='campaign-title'>
                                {BELTS[belt]} Belt Campaign
                            </div>
                            <div className='campaign-levels-wrapper'>
                                {BELTS.map((beltName, beltIdx) => {
                                    if (beltIdx > 0 && beltIdx <= MAX_BELT) {
                                        return this.renderCampaignBeltLevels(
                                            beltIdx, progress, belt === beltIdx
                                        );
                                    }
                                    return null;
                                })}
                            </div>
                            {this.renderCampaignBelts(progress)}
                        </div>
                    )
                }
            </div>
        );
    }

    renderCampaignNoUser() {
        // render an empty campaign state to show behind modal
        const belt = 1, progress = { beltsCompleted: {}, levelsCompleted: {} };

        const loginButton = inIFrame() ?
            <a href='/login?next=/campaign' target='_blank'>Log in</a>
            :
            <a href='/login?next=/campaign'>Log in</a>;

        return (
            <div className='campaign-no-user'>
                <div className='campaign-wrapper'>
                    <div className='campaign-title'>
                        {BELTS[belt]} Belt Campaign
                    </div>
                    <div className='campaign-levels-wrapper'>
                        {this.renderCampaignBeltLevels(belt, progress, true)}
                    </div>
                    {this.renderCampaignBelts(progress)}
                </div>
                <Modal
                    isOpen={true}
                    shouldCloseOnOverlayClick={false}
                    shouldCloseOnEsc={false}
                    className='campaign-no-user-modal'
                >
                    <div className='campaign-no-user-modal-content'>
                        <div className='campaign-no-user-title'>
                            Start your journey to complete 72 challenges and
                        </div>
                        <div className='campaign-no-user-title campaign-no-user-title-last'>
                            {'become a Kung Fu Chess master. '}
                            {loginButton}
                            {' to begin!'}
                        </div>
                        <div
                            className='campaign-cancel-button'
                            onClick={() => {
                                amplitude.track('Cancel Campaign', {
                                    source: 'modal',
                                });

                                this.props.history.push('/');
                            }}
                        >
                            Cancel
                        </div>
                    </div>
                </Modal>
            </div>
        );
    }

    renderCampaignBelts(progress) {
        const currentBelt = this.getCurrentBelt(progress);

        return (
            <div className='campaign-belts'>
                <div className='campaign-belts-row'>
                    {BELTS.map((_, beltIdx) => {
                        return beltIdx > 0 ? this.renderLargeBelt(beltIdx, currentBelt) : null;
                    })}
                </div>
            </div>
        );
    }

    renderLargeBelt(beltIdx, currentBelt) {
        const { belt } = this.state;

        const beltName = BELTS[beltIdx];
        if (beltIdx < currentBelt) {
            // complete belt
            return (
                <Tooltip
                    html={<span>{`${beltName} Belt (Complete)`}</span>}
                    trigger='mouseenter'
                    key={`belt-${beltIdx}`}
                >
                    <div
                        className='campaign-belt campaign-belt-completed'
                        key={beltIdx}
                        onClick={() => this.chooseBelt(beltIdx)}
                    >
                        <img src={`/static/belt-${beltName.toLowerCase()}.png`} />
                    </div>
                </Tooltip>
            );
        } else if (beltIdx > MAX_BELT) {
            // unavailable belt
            return (
                <Tooltip
                    html={<span>{`${beltName} Belt (Coming Soon!)`}</span>}
                    distance={0}
                    trigger='mouseenter'
                    key={`belt-${beltIdx}`}
                >
                    <div
                        className='campaign-belt campaign-belt-unavailable'
                        key={beltIdx}
                    >
                        <img src={`/static/belt-${beltName.toLowerCase()}.png`} />
                    </div>
                </Tooltip>
            );
        } else if (beltIdx === currentBelt) {
            // next belt
            return (
                <Tooltip
                    html={<span>{`${beltName} Belt`}</span>}
                    distance={0}
                    trigger='mouseenter'
                    key={`belt-${beltIdx}`}
                >
                    <div
                        className='campaign-belt campaign-belt-next'
                        key={beltIdx}
                        onClick={() => this.chooseBelt(beltIdx)}
                    >
                        <img src={`/static/belt-${beltName.toLowerCase()}.png`} />
                    </div>
                </Tooltip>
            );
        } else {
            // locked belt
            return (
                <Tooltip
                    html={<span>{`${beltName} Belt (Locked)`}</span>}
                    distance={0}
                    trigger='mouseenter'
                    key={`belt-${beltIdx}`}
                >
                    <div
                        className='campaign-belt campaign-belt-locked'
                        key={beltIdx}
                    >
                        <img src={`/static/belt-${beltName.toLowerCase()}.png`} />
                    </div>
                </Tooltip>
            );
        }
    }

    renderCampaignBeltLevels(belt, progress, isActive) {
        const beltName = BELTS[belt];
        const levelOffset = 8 * (belt - 1);
        const levelClasses = [0, 1, 2, 3, 4, 5, 6, 7, 8].map(idx => {
            let className = ''
            if (levelOffset + idx === 0 || progress.levelsCompleted[levelOffset + idx - 1]) {
                className += 'level-selectable pulse '
            }
            if (progress.levelsCompleted[levelOffset + idx]) {
                className += 'level-complete ';
            }
            return className;
        });
        const pathClasses = [0, 1, 2, 3, 4, 5, 6, 7, 8].map(idx => {
            return progress.levelsCompleted[levelOffset + idx] ? 'path-complete' : '';
        });

        return (
            <CSSTransition
                in={isActive}
                timeout={1000}
                classNames='levels-transition'
                key={`campaign-levels-${belt}`}
            >
                <div className={`campaign-levels ${isActive ? 'campaign-levels-active' : ''}`}>
                    <div className='campaign-levels-row'>
                        <div className='campaign-head' />
                        {this.renderLevel(levelOffset + 0, levelClasses[0])}
                        <div className={`campaign-path ${pathClasses[0]}`} />
                        {this.renderLevel(levelOffset + 1, levelClasses[1])}
                        <div className={`campaign-path ${pathClasses[1]}`} />
                        {this.renderLevel(levelOffset + 2, levelClasses[2])}
                        <div className='campaign-tail' />
                    </div>
                    <div className='campaign-levels-row'>
                        <div className='campaign-head' />
                        {this.renderLevel(levelOffset + 5, levelClasses[5])}
                        <div className={`campaign-path ${pathClasses[4]}`} />
                        {this.renderLevel(levelOffset + 4, levelClasses[4])}
                        <div className={`campaign-path ${pathClasses[3]}`} />
                        {this.renderLevel(levelOffset + 3, levelClasses[3])}
                        <div className={`campaign-tail campaign-tail-path ${pathClasses[2]}`} />
                    </div>
                    <div className='campaign-levels-row'>
                        <div className={`campaign-head campaign-head-path ${pathClasses[5]}`} />
                        {this.renderLevel(levelOffset + 6, levelClasses[6])}
                        <div className={`campaign-path ${pathClasses[6]}`} />
                        {this.renderLevel(levelOffset + 7, levelClasses[7])}
                        <div className={`campaign-path path-end ${pathClasses[7]}`} />
                        <div className='campaign-end'>
                            <img src={`/static/belt-${beltName.toLowerCase()}.png`} />
                        </div>
                    </div>
                </div>
            </CSSTransition>
        );
    }

    renderLevel(level, levelClass) {
        const { progress } = this.state;

        return (
            <Tooltip
                html={<span>{CampaignLevels[level].title}</span>}
                trigger='mouseenter'
            >
                <div
                    className={`campaign-level ${levelClass}`}
                    onClick={() => {
                        if (levelClass.includes('level-selectable')) {
                            amplitude.track('Click Level', {
                                level,
                                isCompleted: progress.levelsCompleted[level] === true,
                            });

                            this.props.startCampaignLevel(level);
                        }
                    }}
                />
            </Tooltip>
        );
    }
};

export default withRouter(Campaign);
