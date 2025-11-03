
// day.js に毎回プラグインやタイムゾーンを設定するのが面倒かつ嵌まりポイントが多いので、
// ここでエクスポートする day.js を使う（Worker でも安全に使えるように依存を最小化）
// ややこしすぎるので KonomiTV 内ではブラウザのタイムゾーンに関わらず、常に Asia/Tokyo として扱う
// ref: https://github.com/iamkun/dayjs/issues/1227#issuecomment-917720826
// ref: https://zenn.dev/taigakiyokawa/articles/20221122-dayjs-timezone

import dayjsOriginal from 'dayjs';
import ja from 'dayjs/locale/ja';
import duration from 'dayjs/plugin/duration';
import isBetween from 'dayjs/plugin/isBetween';
import isSameOrAfter from 'dayjs/plugin/isSameOrAfter';
import isSameOrBefore from 'dayjs/plugin/isSameOrBefore';
import timezone from 'dayjs/plugin/timezone';
import utc from 'dayjs/plugin/utc';

import type { ConfigType, Dayjs } from 'dayjs';

// プラグインをセットアップ
dayjsOriginal.extend(duration);
dayjsOriginal.extend(isBetween);
dayjsOriginal.extend(isSameOrAfter);
dayjsOriginal.extend(isSameOrBefore);
dayjsOriginal.extend(utc);
dayjsOriginal.extend(timezone);
// ロケール/タイムゾーン（固定）
dayjsOriginal.locale(ja);
dayjsOriginal.tz.setDefault('Asia/Tokyo');

// KonomiTV では tz() の実行コストが大きいため、デフォルト TZ を固定して通常の dayjs() を返す
export const dayjs = (date?: ConfigType): Dayjs => dayjsOriginal(date);
export { dayjsOriginal };
