from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "recorded_videos" ADD COLUMN "encoded_file_path" TEXT;
        ALTER TABLE "recorded_videos" ADD COLUMN "is_original_file_deleted" INTEGER NOT NULL DEFAULT 0;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "recorded_videos" DROP COLUMN "encoded_file_path";
        ALTER TABLE "recorded_videos" DROP COLUMN "is_original_file_deleted";
    """
