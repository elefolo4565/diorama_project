#include "FDGameMode.h"

#include "EngineUtils.h"
#include "FDBikePawn.h"
#include "FDGameMenu.h"
#include "FDRegions.h"
#include "FDTimeOfDay.h"
#include "GameFramework/PlayerStart.h"
#include "Engine/PlayerStartPIE.h"

AFDGameMode::AFDGameMode()
{
	DefaultPawnClass = AFDBikePawn::StaticClass();
}

void AFDGameMode::StartPlay()
{
	// Super の中で各アクターの BeginPlay が呼ばれるので、その前に置く。起動画面には時刻の切り替えは要らない
	if (UWorld* World = GetWorld(); World && !FFDRegions::IsStartMap(World) && !TActorIterator<AFDTimeOfDay>(World))
	{
		World->SpawnActor<AFDTimeOfDay>();
	}
	// Tab のメニューと M の拡大マップ
	if (UWorld* World = GetWorld(); World && !TActorIterator<AFDGameMenu>(World))
	{
		World->SpawnActor<AFDGameMenu>();
	}
	Super::StartPlay();
}

bool AFDGameMode::PlayerCanRestart_Implementation(APlayerController* Player)
{
	// 起動画面ではバイクを出さない (地域を選ぶとそのレベルで出る)
	if (FFDRegions::IsStartMap(GetWorld()))
	{
		return false;
	}
	return Super::PlayerCanRestart_Implementation(Player);
}

AActor* AFDGameMode::ChoosePlayerStart_Implementation(AController* Player)
{
	// エディタの再生は既定で「今のカメラの位置から」始まる (PlayerStartPIE)。
	// カメラが地面の下や海の上だと走れないので、レベルの PlayerStart (県道54号の上) を優先する
	if (UWorld* World = GetWorld())
	{
		for (TActorIterator<APlayerStart> It(World); It; ++It)
		{
			if (!It->IsA<APlayerStartPIE>())
			{
				return *It;
			}
		}
	}
	return Super::ChoosePlayerStart_Implementation(Player);
}
