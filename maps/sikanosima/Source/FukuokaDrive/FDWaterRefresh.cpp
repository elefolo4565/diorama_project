#include "FDWaterRefresh.h"

#include "EngineUtils.h"
#include "HAL/PlatformTime.h"
#include "WaterBodyActor.h"
#include "WaterBodyComponent.h"
#include "WaterZoneActor.h"

AFDWaterRefresh::AFDWaterRefresh()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.TickInterval = 0.5f;
	SetHidden(true);
}

void AFDWaterRefresh::PostLoad()
{
	Super::PostLoad();
	Restart();
}

void AFDWaterRefresh::BeginPlay()
{
	Super::BeginPlay();
	Restart();
}

void AFDWaterRefresh::Restart()
{
	StartTime = -1.0;
	NextRefresh = 0;
}

void AFDWaterRefresh::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	if (NextRefresh >= RefreshTimes.Num())
	{
		return;
	}
	// エディタではゲームの時間が進まないので、実際の経過時間で数える
	const double Now = FPlatformTime::Seconds();
	if (StartTime < 0.0)
	{
		StartTime = Now;
	}
	if (Now - StartTime >= RefreshTimes[NextRefresh])
	{
		++NextRefresh;
		RefreshWaterZones();
	}
}

void AFDWaterRefresh::RefreshWaterZones() const
{
	UWorld* World = GetWorld();
	if (!World)
	{
		return;
	}
	// 読み込み直後は Ocean が WaterZone に登録されていない (WaterZone の水の一覧が空) ので、先に登録し直させる。
	// WaterZone の範囲を変えた時にエンジンがしていることと同じ (AWaterZone::OnExtentChanged)
	for (TActorIterator<AWaterBody> It(World); It; ++It)
	{
		if (UWaterBodyComponent* Body = It->GetWaterBodyComponent())
		{
			Body->UpdateWaterZones();
		}
	}
	for (TActorIterator<AWaterZone> It(World); It; ++It)
	{
		It->MarkForRebuild(EWaterZoneRebuildFlags::All, this);
	}
}
