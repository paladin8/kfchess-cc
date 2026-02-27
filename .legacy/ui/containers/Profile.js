import * as amplitude from '@amplitude/analytics-browser';
import React, { Component } from 'react';
import { Link } from 'react-router-dom';
import moment from 'moment';
import { Tooltip } from 'react-tippy';

import ProfilePic from './ProfilePic.js';
import SpeedIcon from './SpeedIcon.js';
import Spinner from './Spinner.js';
import UserDisplay from './UserDisplay.js';
import { BELTS, MAX_BELT } from '../util/CampaignLevels.js';
import * as Time from '../util/Time.js';

const RATING_TYPES = ['standard', 'lightning'];

export default class Profile extends Component {

    constructor(props) {
        super(props);

        this.state = {
            fetching: true,
            historyFetching: true,
            username: null,
            showEditUsername: false,
            editingUsername: false,
            showEditProfilePic: false,
            campaignProgress: null,
            history: null,
        };

        this.usernameInput = null;
        this.profilePicInput = null;

        this.saveUsername = this.saveUsername.bind(this);
        this.saveProfilePic = this.saveProfilePic.bind(this);
    }

    componentWillMount() {
        this.fetchUser(this.props);
    }

    componentDidMount() {
        this.fetchCampaignInfo(this.props);
        this.fetchHistory(this.props);
    }

    componentWillReceiveProps(nextProps) {
        const userId = this.props.match.params.userId;
        const nextUserId = nextProps.match.params.userId;
        if (userId === nextUserId) {
            return;
        }

        this.fetchUser(nextProps);
        this.fetchCampaignInfo(nextProps);
        this.fetchHistory(nextProps);
    }

    fetchUser(props) {
        const { match, user, knownUsers } = props;
        const userId = match.params.userId;
        const isSelf = Boolean(user && match.params.userId === user.userId);

        amplitude.track('Visit Profile Page', {
            userId: match.params.userId,
            isSelf,
        });

        this.setState({ fetching: true });
        this.props.fetchUserInfo([userId], () => {
            this.setState({ fetching: false });
        });
    }

    fetchCampaignInfo(props) {
        const { match } = props;
        const userId = match.params.userId;

        this.props.fetchCampaignInfo(userId, data => {
            this.setState({ campaignProgress: data.progress });
        });
    }

    fetchHistory(props) {
        const { match, user } = props;

        this.setState({ historyFetching: true });
        this.props.getUserGameHistory(match.params.userId, 0, 100, history => {
            this.setState({
                history,
                historyFetching: false,
            });
        });
    }

    saveUsername() {
        const { username } = this.state;
        const { user } = this.props;

        if (username !== user.username) {
            this.props.updateUser(username, () => {
                this.setState({
                    username: null,
                    editingUsername: false,
                });
            });
        } else {
            this.setState({
                username: null,
                editingUsername: false,
            });
        }
    }

    saveProfilePic() {
        const reader = new FileReader();

        reader.onload = (e) => {
            const data = e.currentTarget.result;

            if (data) {
                this.props.uploadProfilePic(data, () => {});
            }
        };

        const file = this.profilePicInput.files[0];
        reader.readAsArrayBuffer(file);
    }

    render() {
        const { fetching } = this.state;
        const { match, user, knownUsers } = this.props;
        const userId = match.params.userId;
        const currUser = knownUsers[userId];
        const isMe = user && user.userId === userId;

        return (
            <div className='profile'>
                {fetching ?
                    <Spinner />
                    :
                    <div className='profile-wrapper'>
                        {currUser ?
                            this.renderProfile(currUser, isMe)
                            :
                            `User ${userId} not found.`
                        }
                    </div>
                }
            </div>
        );
    }

    renderProfile(currUser, isMe) {
        const {
            fetching,
            username,
            showEditUsername,
            editingUsername,
            showEditProfilePic,
            campaignProgress,
        } = this.state;
        const { knownUsers } = this.props;

        let belt = 0;
        while (campaignProgress && belt < MAX_BELT && campaignProgress.beltsCompleted[belt + 1]) {
            belt++;
        }
        const beltName = BELTS[belt];

        return (
            <div className='profile-content'>
                <div className='profile-header'>
                    <div
                        className='profile-pic-wrapper'
                        onMouseEnter={() => isMe && this.setState({ showEditProfilePic: true })}
                        onMouseLeave={() => isMe && this.setState({ showEditProfilePic: false })}
                    >
                        <ProfilePic className='profile-profile-pic' user={currUser} />
                        {showEditProfilePic &&
                            <div
                                className='profile-pic-edit'
                                onClick={() => {
                                    amplitude.track('Click Edit Profile Pic');

                                    this.profilePicInput.click()
                                }}
                            >
                                <i className='fas fa-camera' />
                            </div>
                        }
                        <input
                            ref={input => this.profilePicInput = input}
                            type='file'
                            accept='image/*'
                            onChange={this.saveProfilePic}
                            style={{ display: 'none' }}
                        />
                    </div>
                    <div className='profile-user-info'>
                        <div className='profile-user-info-left'>
                            <div
                                className='profile-username'
                                onMouseEnter={() => isMe && this.setState({ showEditUsername: true })}
                                onMouseLeave={() => isMe && this.setState({ showEditUsername: false })}
                                onClick={() => {
                                    if (isMe && !editingUsername) {
                                        amplitude.track('Click Edit Username');

                                        this.setState({
                                            editingUsername: true,
                                            username: currUser.username,
                                        }, () => {
                                            this.usernameInput.focus();
                                        });
                                    }
                                }}
                            >
                                {!editingUsername && <div className='profile-username-text'>{currUser.username}</div>}
                                {editingUsername &&
                                    <input
                                        ref={input => this.usernameInput = input}
                                        value={username}
                                        maxLength={24}
                                        onChange={(e) => this.setState({ username: e.target.value })}
                                        onKeyPress={(e) => e.key === 'Enter' && this.saveUsername()}
                                    />
                                }
                                {showEditUsername && !editingUsername &&
                                    <div className='profile-edit-username'><i className='far fa-edit' /></div>
                                }
                                {editingUsername &&
                                    <div
                                        className='profile-edit-username'
                                        onClick={this.saveUsername}
                                    >
                                        <i className='far fa-save' />
                                    </div>
                                }
                            </div>
                            <div className='profile-ratings'>
                                {RATING_TYPES.map(type => {
                                    return (
                                        <div className='profile-rating' key={type}>
                                            <div className='profile-rating-type'>{type}</div>
                                            <div className='profile-rating-value'>
                                                {currUser.ratings[type] || 'Unrated'}
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                        <div className='profile-user-info-right'>
                            {campaignProgress !== null &&
                                <img src={`/static/belt-${beltName.toLowerCase()}.png`} />
                            }
                        </div>
                    </div>
                </div>
                {!fetching && this.renderHistory()}
            </div>
        );
    }

    renderHistory() {
        const { historyFetching, history } = this.state;
        const { knownUsers } = this.props;

        return (
            <div className='profile-history'>
            <div className='profile-history-title'>Game History</div>
            {historyFetching ?
                <Spinner />
                :
                <div className='profile-history-table-wrapper'>
                    {history.length === 0 &&
                        <div className='profile-history-no-games'>No games played yet!</div>
                    }
                    {history.length > 0 &&
                        <table className='profile-history-table'>
                            <tbody>
                                {history.map(h => {
                                    const gameTime = moment.utc(h.gameTime);
                                    const gameInfo = h.gameInfo;

                                    const result = gameInfo.winner <= 0 ? 'Draw' : (
                                        gameInfo.player === gameInfo.winner ? 'Won' : 'Lost'
                                    );

                                    let resultColor = '';
                                    if (result === 'Won') {
                                        resultColor = '#7bcc70';
                                    } else if (result === 'Lost') {
                                        resultColor = 'red';
                                    }

                                    return (
                                        <tr className='profile-history-row' key={h.historyId}>
                                            <td
                                                className='profile-history-time'
                                            >
                                                <Tooltip
                                                    title={gameTime.local().format('YYYY-MM-DD hh:mm A')}
                                                >
                                                    {gameTime.fromNow()}
                                                </Tooltip>
                                            </td>
                                            <td className='profile-history-speed'>
                                                <SpeedIcon speed={gameInfo.speed} iconOnly={true} rated={false} />
                                            </td>
                                            <td className='profile-history-opponent'>
                                                <div>vs</div>
                                                {gameInfo.opponents.map(o => {
                                                    return <UserDisplay value={o} knownUsers={knownUsers} />;
                                                })[0]}
                                            </td>
                                            <td
                                                className='profile-history-result'
                                                style={{ color: resultColor }}
                                            >
                                                {result}
                                            </td>
                                            <td className='profile-history-length'>
                                                {Time.renderGameTime(gameInfo.ticks)}
                                            </td>
                                            <td className='profile-history-replay'>
                                                <Tooltip
                                                    title='Replay'
                                                    distance={5}
                                                >
                                                    <Link
                                                        to={`/replay/${gameInfo.historyId}`}
                                                        onClick={() => {
                                                            amplitude.track('Click Watch Replay', {
                                                                source: 'profile',
                                                                historyId: gameInfo.historyId,
                                                            });
                                                        }}
                                                    >
                                                        <i className='fas fa-eye' />
                                                    </Link>
                                                </Tooltip>
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    }
                </div>
            }
        </div>
        );
    }
};
