const assert = require('node:assert/strict');
const path = require('node:path');
const sharp = require(process.argv[2] || 'sharp');
(async () => {
  const dir = process.argv[3] ? path.resolve(process.argv[3]) : path.join(__dirname, '..', 'static', 'mira');
  for (const state of ['idle','blinking','blushing','thinking','smiling','sad','confused','sad_confused','angry']) {
    const mood = state === 'blinking' ? 'idle' : state;
    const actual = await sharp(path.join(dir, state + '.webp'), {page:1}).ensureAlpha().raw().toBuffer({resolveWithObject:true});
    const expected = await sharp(path.join(dir, mood + '_blink.png')).ensureAlpha().raw().toBuffer({resolveWithObject:true});
    assert.equal(actual.info.width, expected.info.width, state);
    assert.equal(actual.info.height, expected.info.height, state);
    for(let p=0;p<actual.data.length;p+=4) {
      assert.equal(actual.data[p+3], expected.data[p+3], state + ' alpha');
      if(expected.data[p+3]) for(let c=0;c<3;c++) assert.equal(actual.data[p+c],expected.data[p+c],state + ' blink pixel');
    }
    console.log(state + ': encoded blink matches its own mood');
  }
})().catch(e=>{console.error(e);process.exitCode=1});
