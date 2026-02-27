import * as PIXI from 'pixi.js';

import spritesImg from '../assets/chess-sprites.png'

function getSprite(image, x, y, width, height) {
	const texture = PIXI.Texture.fromImage(image);
	return new PIXI.Sprite(new PIXI.Texture(texture, new PIXI.Rectangle(x, y, width, height)));
}

const sprites = {
	P1: () => getSprite(spritesImg, 45, 19, 100, 100),
	N1: () => getSprite(spritesImg, 145, 15, 100, 100),
	B1: () => getSprite(spritesImg, 248, 16, 100, 100),
	R1: () => getSprite(spritesImg, 346, 13, 100, 100),
	Q1: () => getSprite(spritesImg, 445, 13, 100, 100),
	K1: () => getSprite(spritesImg, 545, 15, 100, 100),
	P2: () => getSprite(spritesImg, 45, 117, 100, 100),
	N2: () => getSprite(spritesImg, 145, 115, 100, 100),
	B2: () => getSprite(spritesImg, 248, 115, 100, 100),
	R2: () => getSprite(spritesImg, 348, 115, 100, 100),
	Q2: () => getSprite(spritesImg, 446, 115, 100, 100),
	K2: () => getSprite(spritesImg, 545, 115, 100, 100),
};

export default sprites;
