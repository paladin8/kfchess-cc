const path = require('path');
const webpack = require('webpack');
const merge = require('webpack-merge');
const common = require('./webpack.common.config.js');

const parentDir = path.join(__dirname, '../');

module.exports = merge(common, {
    mode: 'development',
    plugins: [
        new webpack.DefinePlugin({
            AMPLITUDE_API_KEY: JSON.stringify('ad42e8caa9b2ee9e7c079085c9a783b7'),
            EXPERIMENT_API_KEY: JSON.stringify('client-Nrhg49woXplMfS7KFJBVcqU7kDfBU8c8'),
        }),
    ],
    devtool: 'inline-source-map',
    devServer: {
        port: 8081,
        contentBase: parentDir,
        historyApiFallback: true,
        proxy: {
            '/api/*': {
                target: 'http://localhost:5001/',
                secure: false,
            },
            '/login': {
                target: 'http://localhost:5001/',
                secure: false,
            },
            '/logout': {
                target: 'http://localhost:5001/',
                secure: false,
            },
            '/socket.io': {
                target: 'http://localhost:5001/',
                secure: false,
            },
        },
    },
});
