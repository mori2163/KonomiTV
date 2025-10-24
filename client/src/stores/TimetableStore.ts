import { defineStore } from 'pinia';

import { ChannelType } from '@/services/Channels';
import Reservations from '@/services/Reservations';
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
        // 録画予約されている番組IDの配列
        reserved_program_ids: [] as string[],
        // 番組IDから録画予約IDへのマップ (削除時に必要) - オブジェクトとして保持
        program_id_to_reservation_id: {} as Record<string, number>,
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
         * 録画予約情報を取得して、予約されている番組IDのセットを更新する
         */
        async fetchReservations() {
            try {
                const reservations = await Reservations.fetchReservations();
                console.log('[TimetableStore] 録画予約情報を取得:', reservations);
                if (reservations) {

                    // 録画予約されている番組のIDを抽出して配列に格納
                    this.reserved_program_ids = reservations.reservations.map(reservation => reservation.program.id);
                    // 番組IDから録画予約IDへのマップを作成
                    const map_obj: Record<string, number> = {};
                    for (const reservation of reservations.reservations) {
                        map_obj[reservation.program.id] = reservation.id;
                    }
                    this.program_id_to_reservation_id = map_obj;
                } else {
                    this.reserved_program_ids = [];
                    this.program_id_to_reservation_id = {};
                }
            } catch (error) {
                this.reserved_program_ids = [];
                this.program_id_to_reservation_id = {};
            }
        },

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
                // 番組表と録画予約情報を並行取得
                const [timetable_channels] = await Promise.all([
                    Timetable.fetchTimetable(start_time, end_time),
                    this.fetchReservations(),
                ]);
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
