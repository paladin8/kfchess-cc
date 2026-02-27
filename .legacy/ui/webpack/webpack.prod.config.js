const webpack = require('webpack');
const merge = require('webpack-merge');
const common = require('./webpack.common.config.js');

const CompressionPlugin = require('compression-webpack-plugin');
const UglifyJsPlugin = require('uglifyjs-webpack-plugin');

module.exports = merge(common, {
    mode: 'production',
    plugins: [
        new webpack.DefinePlugin({
            AMPLITUDE_API_KEY: JSON.stringify('8f1fcc6159b9141780ea8f019a988366'),
            EXPERIMENT_API_KEY: JSON.stringify('client-giQqL6pQjiwdW6SqxpRWrElu3LouUuSU'),
            'process.env.NODE_ENV': JSON.stringify('production'),
        }),
        new UglifyJsPlugin(),
        new CompressionPlugin(),
    ],
});
