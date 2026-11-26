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
import com.playfinder.app.data.local.entity.SlotEntity;
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
public final class SlotDao_Impl implements SlotDao {
  private final RoomDatabase __db;

  private final EntityInsertionAdapter<SlotEntity> __insertionAdapterOfSlotEntity;

  private final SharedSQLiteStatement __preparedStmtOfDeleteStale;

  public SlotDao_Impl(@NonNull final RoomDatabase __db) {
    this.__db = __db;
    this.__insertionAdapterOfSlotEntity = new EntityInsertionAdapter<SlotEntity>(__db) {
      @Override
      @NonNull
      protected String createQuery() {
        return "INSERT OR REPLACE INTO `slots` (`id`,`sport`,`venue`,`facility`,`date`,`startTime`,`endTime`,`available`,`fetchedAt`) VALUES (nullif(?, 0),?,?,?,?,?,?,?,?)";
      }

      @Override
      protected void bind(@NonNull final SupportSQLiteStatement statement,
          @NonNull final SlotEntity entity) {
        statement.bindLong(1, entity.getId());
        statement.bindString(2, entity.getSport());
        statement.bindString(3, entity.getVenue());
        statement.bindString(4, entity.getFacility());
        statement.bindString(5, entity.getDate());
        statement.bindString(6, entity.getStartTime());
        statement.bindString(7, entity.getEndTime());
        statement.bindLong(8, entity.getAvailable());
        statement.bindLong(9, entity.getFetchedAt());
      }
    };
    this.__preparedStmtOfDeleteStale = new SharedSQLiteStatement(__db) {
      @Override
      @NonNull
      public String createQuery() {
        final String _query = "DELETE FROM slots WHERE fetchedAt < ?";
        return _query;
      }
    };
  }

  @Override
  public Object insertAll(final List<SlotEntity> slots,
      final Continuation<? super Unit> $completion) {
    return CoroutinesRoom.execute(__db, true, new Callable<Unit>() {
      @Override
      @NonNull
      public Unit call() throws Exception {
        __db.beginTransaction();
        try {
          __insertionAdapterOfSlotEntity.insert(slots);
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
  public Flow<List<SlotEntity>> observeBySport(final String sport) {
    final String _sql = "SELECT * FROM slots WHERE sport = ? ORDER BY date, startTime";
    final RoomSQLiteQuery _statement = RoomSQLiteQuery.acquire(_sql, 1);
    int _argIndex = 1;
    _statement.bindString(_argIndex, sport);
    return CoroutinesRoom.createFlow(__db, false, new String[] {"slots"}, new Callable<List<SlotEntity>>() {
      @Override
      @NonNull
      public List<SlotEntity> call() throws Exception {
        final Cursor _cursor = DBUtil.query(__db, _statement, false, null);
        try {
          final int _cursorIndexOfId = CursorUtil.getColumnIndexOrThrow(_cursor, "id");
          final int _cursorIndexOfSport = CursorUtil.getColumnIndexOrThrow(_cursor, "sport");
          final int _cursorIndexOfVenue = CursorUtil.getColumnIndexOrThrow(_cursor, "venue");
          final int _cursorIndexOfFacility = CursorUtil.getColumnIndexOrThrow(_cursor, "facility");
          final int _cursorIndexOfDate = CursorUtil.getColumnIndexOrThrow(_cursor, "date");
          final int _cursorIndexOfStartTime = CursorUtil.getColumnIndexOrThrow(_cursor, "startTime");
          final int _cursorIndexOfEndTime = CursorUtil.getColumnIndexOrThrow(_cursor, "endTime");
          final int _cursorIndexOfAvailable = CursorUtil.getColumnIndexOrThrow(_cursor, "available");
          final int _cursorIndexOfFetchedAt = CursorUtil.getColumnIndexOrThrow(_cursor, "fetchedAt");
          final List<SlotEntity> _result = new ArrayList<SlotEntity>(_cursor.getCount());
          while (_cursor.moveToNext()) {
            final SlotEntity _item;
            final long _tmpId;
            _tmpId = _cursor.getLong(_cursorIndexOfId);
            final String _tmpSport;
            _tmpSport = _cursor.getString(_cursorIndexOfSport);
            final String _tmpVenue;
            _tmpVenue = _cursor.getString(_cursorIndexOfVenue);
            final String _tmpFacility;
            _tmpFacility = _cursor.getString(_cursorIndexOfFacility);
            final String _tmpDate;
            _tmpDate = _cursor.getString(_cursorIndexOfDate);
            final String _tmpStartTime;
            _tmpStartTime = _cursor.getString(_cursorIndexOfStartTime);
            final String _tmpEndTime;
            _tmpEndTime = _cursor.getString(_cursorIndexOfEndTime);
            final int _tmpAvailable;
            _tmpAvailable = _cursor.getInt(_cursorIndexOfAvailable);
            final long _tmpFetchedAt;
            _tmpFetchedAt = _cursor.getLong(_cursorIndexOfFetchedAt);
            _item = new SlotEntity(_tmpId,_tmpSport,_tmpVenue,_tmpFacility,_tmpDate,_tmpStartTime,_tmpEndTime,_tmpAvailable,_tmpFetchedAt);
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

  @Override
  public Flow<List<SlotEntity>> observeBySportAndDate(final String sport, final String from,
      final String to) {
    final String _sql = "SELECT * FROM slots WHERE sport = ? AND date BETWEEN ? AND ? ORDER BY date, startTime";
    final RoomSQLiteQuery _statement = RoomSQLiteQuery.acquire(_sql, 3);
    int _argIndex = 1;
    _statement.bindString(_argIndex, sport);
    _argIndex = 2;
    _statement.bindString(_argIndex, from);
    _argIndex = 3;
    _statement.bindString(_argIndex, to);
    return CoroutinesRoom.createFlow(__db, false, new String[] {"slots"}, new Callable<List<SlotEntity>>() {
      @Override
      @NonNull
      public List<SlotEntity> call() throws Exception {
        final Cursor _cursor = DBUtil.query(__db, _statement, false, null);
        try {
          final int _cursorIndexOfId = CursorUtil.getColumnIndexOrThrow(_cursor, "id");
          final int _cursorIndexOfSport = CursorUtil.getColumnIndexOrThrow(_cursor, "sport");
          final int _cursorIndexOfVenue = CursorUtil.getColumnIndexOrThrow(_cursor, "venue");
          final int _cursorIndexOfFacility = CursorUtil.getColumnIndexOrThrow(_cursor, "facility");
          final int _cursorIndexOfDate = CursorUtil.getColumnIndexOrThrow(_cursor, "date");
          final int _cursorIndexOfStartTime = CursorUtil.getColumnIndexOrThrow(_cursor, "startTime");
          final int _cursorIndexOfEndTime = CursorUtil.getColumnIndexOrThrow(_cursor, "endTime");
          final int _cursorIndexOfAvailable = CursorUtil.getColumnIndexOrThrow(_cursor, "available");
          final int _cursorIndexOfFetchedAt = CursorUtil.getColumnIndexOrThrow(_cursor, "fetchedAt");
          final List<SlotEntity> _result = new ArrayList<SlotEntity>(_cursor.getCount());
          while (_cursor.moveToNext()) {
            final SlotEntity _item;
            final long _tmpId;
            _tmpId = _cursor.getLong(_cursorIndexOfId);
            final String _tmpSport;
            _tmpSport = _cursor.getString(_cursorIndexOfSport);
            final String _tmpVenue;
            _tmpVenue = _cursor.getString(_cursorIndexOfVenue);
            final String _tmpFacility;
            _tmpFacility = _cursor.getString(_cursorIndexOfFacility);
            final String _tmpDate;
            _tmpDate = _cursor.getString(_cursorIndexOfDate);
            final String _tmpStartTime;
            _tmpStartTime = _cursor.getString(_cursorIndexOfStartTime);
            final String _tmpEndTime;
            _tmpEndTime = _cursor.getString(_cursorIndexOfEndTime);
            final int _tmpAvailable;
            _tmpAvailable = _cursor.getInt(_cursorIndexOfAvailable);
            final long _tmpFetchedAt;
            _tmpFetchedAt = _cursor.getLong(_cursorIndexOfFetchedAt);
            _item = new SlotEntity(_tmpId,_tmpSport,_tmpVenue,_tmpFacility,_tmpDate,_tmpStartTime,_tmpEndTime,_tmpAvailable,_tmpFetchedAt);
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
