import React, { Component } from 'react';
import { CSSTransition } from 'react-transition-group'

export default class Alert extends Component {

    constructor(props) {
        super(props);

        this.state = {
            showing: false,
        };
    }

    componentWillReceiveProps(nextProps) {
        if (nextProps.error && (!this.props.error || nextProps.error.id !== this.props.error.id)) {
            this.setState({
                showing: true,
            }, () => {
                // dismiss the alert after 5s
                window.setTimeout(() => {
                    this.setState({
                        showing: false,
                    });
                }, 5000);
            });
        }
    }

    render() {
        const { showing } = this.state;
        const { error } = this.props;

        return (
            <div className='alert'>
                <CSSTransition
                    in={showing}
                    timeout={500}
                    classNames='alert-transition'
                >
                    <div className={`alert-message ${showing ? 'alert-message-showing' : ''}`}>
                        <i className='fas fa-exclamation-circle' />{error && error.message}
                    </div>
                </CSSTransition>
            </div>
        );
    }
};
