#include "FDRegions.h"

#include "Engine/World.h"
#include "Interfaces/IPluginManager.h"
#include "Kismet/GameplayStatics.h"
#include "Misc/ConfigCacheIni.h"
#include "Misc/PackageName.h"
#include "UObject/Package.h"

const TCHAR* const FFDRegions::StartMap = TEXT("/Game/FukuokaDrive/Maps/Start");

namespace
{
	const TCHAR* const RegionCategory = TEXT("Touring Region");
	const TCHAR* const SettingsSection = TEXT("FukuokaDrive.Settings");
}

TArray<FFDRegion> FFDRegions::Find()
{
	TArray<FFDRegion> Out;
	for (const TSharedRef<IPlugin>& Plugin : IPluginManager::Get().GetEnabledPluginsWithContent())
	{
		const FPluginDescriptor& Desc = Plugin->GetDescriptor();
		if (!Desc.Category.Equals(RegionCategory, ESearchCase::IgnoreCase))
		{
			continue;
		}
		FFDRegion Region;
		Region.Name = Plugin->GetName();
		Region.DisplayName = Desc.FriendlyName.IsEmpty() ? Region.Name : Desc.FriendlyName;
		Region.Description = Desc.Description;
		Region.MapPackage = FString::Printf(TEXT("/%s/Maps/%s"), *Region.Name, *Region.Name);
		// まだ組み立てていない地域 (レベルが無い) は出さない
		if (FPackageName::DoesPackageExist(Region.MapPackage))
		{
			Out.Add(MoveTemp(Region));
		}
	}
	Out.Sort([](const FFDRegion& A, const FFDRegion& B) { return A.Name < B.Name; });
	return Out;
}

FString FFDRegions::CurrentMapPackage(const UWorld* World)
{
	if (!World || !World->GetPackage())
	{
		return FString();
	}
	// エディタの再生 (PIE) ではレベル名の頭に UEDPIE_<n>_ が付く
	return UWorld::RemovePIEPrefix(World->GetPackage()->GetName());
}

bool FFDRegions::IsStartMap(const UWorld* World)
{
	return CurrentMapPackage(World) == StartMap;
}

FString FFDRegions::LastRegion()
{
	FString Name;
	GConfig->GetString(SettingsSection, TEXT("LastRegion"), Name, GGameUserSettingsIni);
	return Name;
}

void FFDRegions::Open(UObject* WorldContext, const FFDRegion& Region)
{
	GConfig->SetString(SettingsSection, TEXT("LastRegion"), *Region.Name, GGameUserSettingsIni);
	GConfig->Flush(false, GGameUserSettingsIni);
	UGameplayStatics::OpenLevel(WorldContext, FName(*Region.MapPackage));
}
