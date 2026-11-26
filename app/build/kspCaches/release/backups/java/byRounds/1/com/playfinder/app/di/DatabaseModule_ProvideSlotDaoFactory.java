package com.playfinder.app.di;

import com.playfinder.app.data.local.PlayFinderDatabase;
import com.playfinder.app.data.local.dao.SlotDao;
import dagger.internal.DaggerGenerated;
import dagger.internal.Factory;
import dagger.internal.Preconditions;
import dagger.internal.QualifierMetadata;
import dagger.internal.ScopeMetadata;
import javax.annotation.processing.Generated;
import javax.inject.Provider;

@ScopeMetadata
@QualifierMetadata
@DaggerGenerated
@Generated(
    value = "dagger.internal.codegen.ComponentProcessor",
    comments = "https://dagger.dev"
)
@SuppressWarnings({
    "unchecked",
    "rawtypes",
    "KotlinInternal",
    "KotlinInternalInJava",
    "cast",
    "deprecation"
})
public final class DatabaseModule_ProvideSlotDaoFactory implements Factory<SlotDao> {
  private final Provider<PlayFinderDatabase> dbProvider;

  public DatabaseModule_ProvideSlotDaoFactory(Provider<PlayFinderDatabase> dbProvider) {
    this.dbProvider = dbProvider;
  }

  @Override
  public SlotDao get() {
    return provideSlotDao(dbProvider.get());
  }

  public static DatabaseModule_ProvideSlotDaoFactory create(
      Provider<PlayFinderDatabase> dbProvider) {
    return new DatabaseModule_ProvideSlotDaoFactory(dbProvider);
  }

  public static SlotDao provideSlotDao(PlayFinderDatabase db) {
    return Preconditions.checkNotNullFromProvides(DatabaseModule.INSTANCE.provideSlotDao(db));
  }
}
