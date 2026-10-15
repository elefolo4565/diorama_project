#include "FDInstances.h"

#include "Components/InstancedStaticMeshComponent.h"
#include "Engine/World.h"

AFDInstances::AFDInstances()
{
	PrimaryActorTick.bCanEverTick = false;

	Instances = CreateDefaultSubobject<UInstancedStaticMeshComponent>(TEXT("Instances"));
	Instances->SetMobility(EComponentMobility::Static);
	// バイクの接地判定 (Visibility の線) が木やガードレールの上に乗らないよう、当たり判定は切る
	Instances->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Instances->SetCanEverAffectNavigation(false);
	SetRootComponent(Instances);
}

int32 AFDInstances::SeasonBit(int32 Month)
{
	// 3-5 月 = 春 (ビット 0)、6-8 月 = 夏、9-11 月 = 秋、12-2 月 = 冬
	const int32 Index = (((Month % 12) + 12) % 12) / 3;  // 12-2 月 = 0、3-5 月 = 1、...
	return 1 << ((Index + 3) % 4);
}

void AFDInstances::ApplySeason(int32 Month)
{
	if (SeasonMask != 0)
	{
		SetActorHiddenInGame((SeasonMask & SeasonBit(Month)) == 0);
	}
}

void AFDInstances::PostRegisterAllComponents()
{
	Super::PostRegisterAllComponents();
	// エディタでレベルを開いたとき (と置き直したとき) は、プレイの初めと同じ季節のものだけ見せる
#if WITH_EDITOR
	if (SeasonMask != 0 && GetWorld() && !GetWorld()->IsGameWorld())
	{
		SetIsTemporarilyHiddenInEditor((SeasonMask & SeasonBit(EditorPreviewMonth)) == 0);
	}
#endif
}
