from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "recorded_videos" ADD COLUMN "is_tsreplace_encoded" INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE "recorded_videos" ADD COLUMN "tsreplace_encoded_at" TIMESTAMP;
        ALTER TABLE "recorded_videos" ADD COLUMN "original_video_codec" VARCHAR(255);
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "recorded_videos" DROP COLUMN "is_tsreplace_encoded";
        ALTER TABLE "recorded_videos" DROP COLUMN "tsreplace_encoded_at";
        ALTER TABLE "recorded_videos" DROP COLUMN "original_video_codec";
    """
