import type { ChannelType } from '@/services/Channels';
import type { IRecordedProgram } from '@/services/Videos';

export type OfflineStorageBackend = 'opfs' | 'indexeddb' | 'cache';

export type OfflineDownloadStatus = 'downloading' | 'completed' | 'paused' | 'error';

export interface OfflineSegmentDescriptor {
    sequence: number;
    duration: number;
}

/**
 * オフライン保存用の録画番組データ
 * IndexedDB に保存可能なように、IRecordedProgram から必要な情報だけを抽出したプレーンオブジェクト
 */
export interface OfflineRecordedProgramData {
    id: number;
    video_id: number;
    title: string;
    series_title: string | null;
    episode_number: string | null;
    subtitle: string | null;
    description: string;
    channel_id: string | null;
    channel_name: string;
    channel_display_id: string | null;
    channel_type: ChannelType | null;
    channel_network_id: number | null;
    channel_service_id: number | null;
    channel_transport_stream_id: number | null;
    channel_remocon_id: number | null;
    channel_number: string | null;
    channel_is_radiochannel: boolean | null;
    channel_is_subchannel: boolean | null;
    channel_is_watchable: boolean | null;
    start_time: string;
    end_time: string;
    duration: number;
    genres: { major: string; middle: string; }[];
    video_file_path: string;
    video_file_size: number;
    video_resolution_width: number;
    video_resolution_height: number;
}

export interface OfflineDownloadMetadata {
    id: string;
    video_id: number;
    quality: string;
    is_hevc: boolean;
    save_comments: boolean;
    storage_backend: OfflineStorageBackend;
    status: OfflineDownloadStatus;
    recorded_program: OfflineRecordedProgramData;
    target_duration: number;
    segment_count: number;
    segments: OfflineSegmentDescriptor[];
    total_size: number;
    downloaded_bytes: number;
    created_at: string;
    updated_at: string;
    playlist_path: string;  // ストレージ内のプレイリストへのパス
    has_thumbnail: boolean;  // サムネイルが保存されているかどうか
}

export interface OfflineDownloadProgressUpdate {
    id: string;
    downloaded_segments: number;
    downloaded_bytes: number;
    total_segments: number;
    total_bytes_estimated?: number;
    start_time?: number;  // ダウンロード開始時刻（ミリ秒）
    estimated_remaining_time?: number;  // 推定残り時間（ミリ秒）
}

/**
 * IRecordedProgram をオフライン保存用のプレーンオブジェクトに変換する
 */
export function serializeRecordedProgram(program: IRecordedProgram): OfflineRecordedProgramData {
    // genres 配列を完全にプレーンなオブジェクト配列に変換
    const genres = program.genres.map(genre => ({
        major: String(genre.major),
        middle: String(genre.middle),
    }));

    return {
        id: program.id,
        video_id: program.recorded_video.id,
        title: program.title,
        series_title: program.series_title,
        episode_number: program.episode_number,
        subtitle: program.subtitle,
        description: program.description,
        channel_id: program.channel?.id || null,
        channel_name: program.channel?.name || '不明',
        channel_display_id: program.channel?.display_channel_id ?? null,
        channel_type: program.channel?.type ?? null,
        channel_network_id: program.channel?.network_id ?? null,
        channel_service_id: program.channel?.service_id ?? null,
        channel_transport_stream_id: program.channel?.transport_stream_id ?? null,
        channel_remocon_id: program.channel?.remocon_id ?? null,
        channel_number: program.channel?.channel_number ?? null,
        channel_is_radiochannel: program.channel?.is_radiochannel ?? null,
        channel_is_subchannel: program.channel?.is_subchannel ?? null,
        channel_is_watchable: program.channel?.is_watchable ?? null,
        start_time: program.start_time,
        end_time: program.end_time,
        duration: program.recorded_video.duration,
        genres: genres,
        video_file_path: program.recorded_video.file_path,
        video_file_size: program.recorded_video.file_size,
        video_resolution_width: program.recorded_video.video_resolution_width,
        video_resolution_height: program.recorded_video.video_resolution_height,
    };
}

/**
 * OfflineDownloadMetadata を IndexedDB に保存可能な形式にシリアライズする
 * すべてのプロパティをプレーンなオブジェクトに変換
 */
export function serializeMetadata(metadata: OfflineDownloadMetadata): OfflineDownloadMetadata {
    return {
        id: metadata.id,
        video_id: metadata.video_id,
        quality: metadata.quality,
        is_hevc: metadata.is_hevc,
        save_comments: metadata.save_comments ?? true,
        storage_backend: metadata.storage_backend,
        status: metadata.status,
        recorded_program: JSON.parse(JSON.stringify(metadata.recorded_program)),
        target_duration: metadata.target_duration,
        segment_count: metadata.segment_count,
        segments: metadata.segments.map(seg => ({
            sequence: seg.sequence,
            duration: seg.duration,
        })),
        total_size: metadata.total_size,
        downloaded_bytes: metadata.downloaded_bytes,
        created_at: metadata.created_at,
        updated_at: metadata.updated_at,
        playlist_path: metadata.playlist_path,
        has_thumbnail: metadata.has_thumbnail ?? false,
    };
}
