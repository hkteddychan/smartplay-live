package com.playfinder.app.data.local.dao;

import android.database.Cursor;
import androidx.annotation.NonNull;
import androidx.room.CoroutinesRoom;
import androidx.room.EntityInsertionAdapter;
import androidx.room.RoomDatabase;
import androidx.room.RoomSQLiteQuery;
import androidx.room.SharedSQLiteStatement;
import androidx.room.util.CursorUtil;
import androidx.room.util.DBUtil;
import androidx.sqlite.db.SupportSQLiteStatement;
import com.playfinder.app.data.local.entity.ActivityEntity;
import java.lang.Class;
import java.lang.Exception;
import java.lang.Object;
import java.lang.Override;
import java.lang.String;
import java.lang.SuppressWarnings;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.Callable;
import javax.annotation.processing.Generated;
import kotlin.Unit;
import kotlin.coroutines.Continuation;
import kotlinx.coroutines.flow.Flow;

@Generated("androidx.room.RoomProcessor")
@SuppressWarnings({"unchecked", "deprecation"})
public final class ActivityDao_Impl implements ActivityDao {
  private final RoomDatabase __db;

  private final EntityInsertionAdapter<ActivityEntity> __insertionAdapterOfActivityEntity;

  private final SharedSQLiteStatement __preparedStmtOfDeleteStale;

  public ActivityDao_Impl(@NonNull final RoomDatabase __db) {
    this.__db = __db;
    this.__insertionAdapterOfActivityEntity = new EntityInsertionAdapter<ActivityEntity>(__db) {
      @Override
      @NonNull
      protected String createQuery() {
        return "INSERT OR REPLACE INTO `activities` (`id`,`name`,`type`,`district`,`startDate`,`endDate`,`venue`,`available`,`fetchedAt`) VALUES (?,?,?,?,?,?,?,?,?)";
      }

      @Override
      protected void bind(@NonNull final SupportSQLiteStatement statement,
          @NonNull final ActivityEntity entity) {
        statement.bindString(1, entity.getId());
        statement.bindString(2, entity.getName());
        statement.bindString(3, entity.getType());
        statement.bindString(4, entity.getDistrict());
        statement.bindString(5, entity.getStartDate());
        statement.bindString(6, entity.getEndDate());
        statement.bindString(7, entity.getVenue());
        statement.bindLong(8, entity.getAvailable());
        statement.bindLong(9, entity.getFetchedAt());
      }
    };
    this.__preparedStmtOfDeleteStale = new SharedSQLiteStatement(__db) {
      @Override
      @NonNull
      public String createQuery() {
        final String _query = "DELETE FROM activities WHERE fetchedAt < ?";
        return _query;
      }
    };
  }

  @Override
  public Object insertAll(final List<ActivityEntity> activities,
      final Continuation<? super Unit> $completion) {
    return CoroutinesRoom.execute(__db, true, new Callable<Unit>() {
      @Override
      @NonNull
      public Unit call() throws Exception {
        __db.beginTransaction();
        try {
          __insertionAdapterOfActivityEntity.insert(activities);
          __db.setTransactionSuccessful();
          return Unit.INSTANCE;
        } finally {
          __db.endTransaction();
        }
      }
    }, $completion);
  }

  @Override
  public Object deleteStale(final long cutoff, final Continuation<? super Unit> $completion) {
    return CoroutinesRoom.execute(__db, true, new Callable<Unit>() {
      @Override
      @NonNull
      public Unit call() throws Exception {
        final SupportSQLiteStatement _stmt = __preparedStmtOfDeleteStale.acquire();
        int _argIndex = 1;
        _stmt.bindLong(_argIndex, cutoff);
        try {
          __db.beginTransaction();
          try {
            _stmt.executeUpdateDelete();
            __db.setTransactionSuccessful();
            return Unit.INSTANCE;
          } finally {
            __db.endTransaction();
          }
        } finally {
          __preparedStmtOfDeleteStale.release(_stmt);
        }
      }
    }, $completion);
  }

  @Override
  public Flow<List<ActivityEntity>> observe(final String sport, final String district,
      final String from) {
    final String _sql = "SELECT * FROM activities WHERE (? = '' OR type = ?) AND (? = '' OR district = ?) AND startDate >= ? ORDER BY startDate";
    final RoomSQLiteQuery _statement = RoomSQLiteQuery.acquire(_sql, 5);
    int _argIndex = 1;
    _statement.bindString(_argIndex, sport);
    _argIndex = 2;
    _statement.bindString(_argIndex, sport);
    _argIndex = 3;
    _statement.bindString(_argIndex, district);
    _argIndex = 4;
    _statement.bindString(_argIndex, district);
    _argIndex = 5;
    _statement.bindString(_argIndex, from);
    return CoroutinesRoom.createFlow(__db, false, new String[] {"activities"}, new Callable<List<ActivityEntity>>() {
      @Override
      @NonNull
      public List<ActivityEntity> call() throws Exception {
        final Cursor _cursor = DBUtil.query(__db, _statement, false, null);
        try {
          final int _cursorIndexOfId = CursorUtil.getColumnIndexOrThrow(_cursor, "id");
          final int _cursorIndexOfName = CursorUtil.getColumnIndexOrThrow(_cursor, "name");
          final int _cursorIndexOfType = CursorUtil.getColumnIndexOrThrow(_cursor, "type");
          final int _cursorIndexOfDistrict = CursorUtil.getColumnIndexOrThrow(_cursor, "district");
          final int _cursorIndexOfStartDate = CursorUtil.getColumnIndexOrThrow(_cursor, "startDate");
          final int _cursorIndexOfEndDate = CursorUtil.getColumnIndexOrThrow(_cursor, "endDate");
          final int _cursorIndexOfVenue = CursorUtil.getColumnIndexOrThrow(_cursor, "venue");
          final int _cursorIndexOfAvailable = CursorUtil.getColumnIndexOrThrow(_cursor, "available");
          final int _cursorIndexOfFetchedAt = CursorUtil.getColumnIndexOrThrow(_cursor, "fetchedAt");
          final List<ActivityEntity> _result = new ArrayList<ActivityEntity>(_cursor.getCount());
          while (_cursor.moveToNext()) {
            final ActivityEntity _item;
            final String _tmpId;
            _tmpId = _cursor.getString(_cursorIndexOfId);
            final String _tmpName;
            _tmpName = _cursor.getString(_cursorIndexOfName);
            final String _tmpType;
            _tmpType = _cursor.getString(_cursorIndexOfType);
            final String _tmpDistrict;
            _tmpDistrict = _cursor.getString(_cursorIndexOfDistrict);
            final String _tmpStartDate;
            _tmpStartDate = _cursor.getString(_cursorIndexOfStartDate);
            final String _tmpEndDate;
            _tmpEndDate = _cursor.getString(_cursorIndexOfEndDate);
            final String _tmpVenue;
            _tmpVenue = _cursor.getString(_cursorIndexOfVenue);
            final int _tmpAvailable;
            _tmpAvailable = _cursor.getInt(_cursorIndexOfAvailable);
            final long _tmpFetchedAt;
            _tmpFetchedAt = _cursor.getLong(_cursorIndexOfFetchedAt);
            _item = new ActivityEntity(_tmpId,_tmpName,_tmpType,_tmpDistrict,_tmpStartDate,_tmpEndDate,_tmpVenue,_tmpAvailable,_tmpFetchedAt);
            _result.add(_item);
          }
          return _result;
        } finally {
          _cursor.close();
        }
      }

      @Override
      protected void finalize() {
        _statement.release();
      }
    });
  }

  @NonNull
  public static List<Class<?>> getRequiredConverters() {
    return Collections.emptyList();
  }
}
