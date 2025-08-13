import { defineStore } from 'pinia';

import { ChannelType } from '@/services/Channels';
import Timetable from '@/services/Timetable';
import { ITimetableChannel } from '@/services/Timetable';

export const useTimetableStore = defineStore('timetable', {
    state: () => ({
        // 番組表のデータ
        _timetable_channels: null as ITimetableChannel[] | null,
        // 現在表示している日付
        current_date: new Date(),
        // 現在選択中のチャンネルタイプ
        selected_channel_type: 'ALL' as 'ALL' | ChannelType,
        // ロード中フラグ
        is_loading: false,
    }),
    getters: {
        /**
         * 表示用にフィルタリングされた番組表のデータ
         */
        timetable_channels(state): ITimetableChannel[] | null {
            if (!state._timetable_channels) {
                return null;
            }
            if (state.selected_channel_type === 'ALL') {
                return state._timetable_channels;
            }
            return state._timetable_channels.filter(channel => channel.channel.type === state.selected_channel_type);
        }
    },
    actions: {
        /**
         * 番組表のデータを取得・更新する
         */
        async fetchTimetable() {
            if (this.is_loading) return;
            this.is_loading = true;

            // 表示する期間を計算 (今日の 04:00:00 から 24時間)
            const start_time = new Date(this.current_date);
            start_time.setHours(4, 0, 0, 0);
            const end_time = new Date(start_time);
            end_time.setDate(end_time.getDate() + 1);

            try {
                const timetable_channels = await Timetable.fetchTimetable(start_time, end_time);
                this._timetable_channels = timetable_channels;
            } catch (error) {
                console.error(error);
                this._timetable_channels = null;
            } finally {
                this.is_loading = false;
            }
        },

        /**
         * 表示する日付を前日にする
         */
        setPreviousDate() {
            const newDate = new Date(this.current_date);
            newDate.setDate(newDate.getDate() - 1);
            this.current_date = newDate;
            this.fetchTimetable();
        },

        /**
         * 表示する日付を翌日にする
         */
        setNextDate() {
            const newDate = new Date(this.current_date);
            newDate.setDate(newDate.getDate() + 1);
            this.current_date = newDate;
            this.fetchTimetable();
        },

        /**
         * 表示する日付を今日にする
         */
        setCurrentDate() {
            this.current_date = new Date();
            this.fetchTimetable();
        },

        /**
         * 表示するチャンネルタイプを設定する
         * @param type 設定するチャンネルタイプ
         */
        setChannelType(type: 'ALL' | ChannelType) {
            this.selected_channel_type = type;
        },

        /**
         * EPG（番組情報）を取得する
         */
        async updateEPG() {
            if (this.is_loading) return;
            this.is_loading = true;

            try {
                const success = await Timetable.updateEPG();
                if (!success) {
                    throw new Error('EPGの取得に失敗しました。');
                }
                // EPG取得後に番組表を再取得
                await this.fetchTimetable();
            } catch (error) {
                console.error('EPG 取得エラー:', error);
                // エラーを上位に投げ直す
                throw error;
            } finally {
                this.is_loading = false;
            }
        },

        /**
         * EPG（番組情報）を再読み込みする
         */
        async reloadEPG() {
            if (this.is_loading) return;
            this.is_loading = true;

            try {
                const success = await Timetable.reloadEPG();
                if (!success) {
                    throw new Error('EPGの再読み込みに失敗しました。');
                }
                // EPG再読み込み後に番組表を再取得
                await this.fetchTimetable();
            } catch (error) {
                console.error('EPG再読み込みエラー:', error);
                // エラーを上位に投げ直す
                throw error;
            } finally {
                this.is_loading = false;
            }
        }
    }
});

export default useTimetableStore;
